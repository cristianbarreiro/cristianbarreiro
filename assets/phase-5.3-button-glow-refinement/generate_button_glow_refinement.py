"""Create a separate Phase 5.3 copy with an outer-only portfolio halo."""

from __future__ import annotations

import base64
import copy
import hashlib
import importlib.util
import io
import json
import math
import shutil
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
PREVIEW = OUT / "preview"
LAYERS = OUT / "layers"
SOURCE = ROOT / "assets" / "image.png"
PHASE52 = ROOT / "assets" / "phase-5.2-microinteractions"
BASE_JSON = PHASE52 / "profile-banner-phase-5.2.json"
BASE_SVG = PHASE52 / "profile-banner-phase-5.2.svg"
W, H = 1672, 941
PREVIEW_SIZE = (1000, 563)
PREVIEW_FRAMES = 135
PREVIEW_FPS = 15
MIN_OPACITY = 12.0
MAX_OPACITY = 30.0
GLOW_PERIOD = 3.0  # Three complete cycles over the 9-second Lottie composition.
GLOW_BLUR_RADII = (4.0, 9.0)
GLOW_BLUR_WEIGHTS = (0.82, 0.50)
GLOW_ALPHA_GAIN = 2.7
OUTSIDE_FADE_PX = 3.0
SOURCE_MASK_BAND = (-5.0, 2.5)
SOURCE_MASK_CROP = (994, 432, 1614, 624)
SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)


def import_phase52():
    path = PHASE52 / "generate_microinteractions.py"
    spec = importlib.util.spec_from_file_location("phase52_renderer", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load Phase 5.2 helpers at {path}")
    module = importlib.util.module_from_spec(spec)
    prior = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = prior
    # Keep all timing helpers aligned with this version without touching 5.2.
    module.GLOW_MIN_OPACITY = MIN_OPACITY
    module.GLOW_MAX_OPACITY = MAX_OPACITY
    module.GLOW_PERIOD_SECONDS = GLOW_PERIOD
    return module


def smoothstep(value: float) -> float:
    t = max(0.0, min(1.0, value))
    return t * t * (3 - 2 * t)


def png_bytes(image: Image.Image) -> bytes:
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True, compress_level=9)
    return output.getvalue()


def make_outer_halo(source: Image.Image, phase52) -> tuple[Image.Image, dict]:
    """Blur only genuine border-color pixels, then mask strictly outside the rim."""
    x0, y0, x1, y1 = SOURCE_MASK_CROP
    crop = source.crop(SOURCE_MASK_CROP).convert("RGB")
    width, height = crop.size
    pixels = crop.load()
    core = Image.new("L", (width, height), 0)
    core_px = core.load()
    rect = phase52.BUTTON_RECT
    side_pixels = {"top": 0, "right": 0, "bottom": 0, "left": 0}
    corner_pixels = {"top_left": 0, "top_right": 0, "bottom_left": 0, "bottom_right": 0}

    for cy in range(height):
        y = y0 + cy + 0.5
        for cx in range(width):
            x = x0 + cx + 0.5
            distance = phase52._rounded_rect_distance(x, y)
            if not SOURCE_MASK_BAND[0] <= distance <= SOURCE_MASK_BAND[1]:
                continue
            red, green, blue = pixels[cx, cy]
            bright = max(red, green, blue)
            chroma = bright - min(red, green, blue)
            if bright < 110 or chroma < 46:
                continue
            luminance_weight = max(0.0, min(1.0, (bright - 90) / 135))
            chroma_weight = max(0.0, min(1.0, chroma / 120))
            alpha = round(255 * luminance_weight * chroma_weight)
            if alpha < 24:
                continue
            core_px[cx, cy] = alpha
            left, top, right, bottom = rect
            if abs(y - top) <= 6 and left + 32 < x < right - 32:
                side_pixels["top"] += 1
            if abs(x - right) <= 6 and top + 32 < y < bottom - 32:
                side_pixels["right"] += 1
            if abs(y - bottom) <= 6 and left + 32 < x < right - 32:
                side_pixels["bottom"] += 1
            if abs(x - left) <= 6 and top + 32 < y < bottom - 32:
                side_pixels["left"] += 1
            if x < (left + right) / 2:
                corner = "top_left" if y < (top + bottom) / 2 else "bottom_left"
            else:
                corner = "top_right" if y < (top + bottom) / 2 else "bottom_right"
            corner_pixels[corner] += 1

    if not core.getbbox():
        raise AssertionError("No existing colored portfolio-border pixels were found")
    if any(value < 15 for value in side_pixels.values()):
        raise AssertionError(f"The source-border mask missed a side: {side_pixels}")
    if any(value < 2 for value in corner_pixels.values()):
        raise AssertionError(f"The source-border mask missed a rounded corner: {corner_pixels}")

    alpha_blurs = [core.filter(ImageFilter.GaussianBlur(radius))
                   for radius in GLOW_BLUR_RADII]
    alpha_pixels = [layer.load() for layer in alpha_blurs]
    source_channels = [crop.getchannel(channel) for channel in range(3)]
    premultiplied = [
        [ImageChops.multiply(channel, core).filter(ImageFilter.GaussianBlur(radius))
         for radius in GLOW_BLUR_RADII]
        for channel in source_channels
    ]
    premultiplied_pixels = [[layer.load() for layer in channel_layers]
                            for channel_layers in premultiplied]

    glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    glow_px = glow.load()
    nonzero_inside = 0
    min_positive_distance = float("inf")
    for cy in range(height):
        y = y0 + cy + 0.5
        for cx in range(width):
            x = x0 + cx + 0.5
            distance = phase52._rounded_rect_distance(x, y)
            # No alpha is permitted on the contour or inside the button.
            if distance <= 0:
                continue
            gate = smoothstep(distance / OUTSIDE_FADE_PX)
            if gate <= 0:
                continue
            blurred = [layer[cx, cy] for layer in alpha_pixels]
            mixed_alpha = sum(value * weight for value, weight in zip(blurred, GLOW_BLUR_WEIGHTS))
            if mixed_alpha <= 1:
                continue
            output_alpha = min(255, round(mixed_alpha * GLOW_ALPHA_GAIN * gate))
            if output_alpha <= 1:
                continue
            color = []
            for channel_layers in premultiplied_pixels:
                mixed = sum(channel_layers[i][cx, cy] * GLOW_BLUR_WEIGHTS[i]
                            for i in range(len(GLOW_BLUR_RADII)))
                color.append(max(0, min(255, round(mixed * 255 / mixed_alpha))))
            glow_px[cx, cy] = (*color, output_alpha)
            min_positive_distance = min(min_positive_distance, distance)
            if distance < 0:
                nonzero_inside += 1

    alpha_channel = glow.getchannel("A")
    stats = {
        "method": "Gaussian bloom from source border pixels, clipped to the exterior of the measured rounded-rectangle contour",
        "source_mask_pixels": sum(value > 0 for value in core.get_flattened_data()),
        "side_coverage_pixels": side_pixels,
        "rounded_corner_coverage_pixels": corner_pixels,
        "outside_fade_px": OUTSIDE_FADE_PX,
        "blur_radii_px": list(GLOW_BLUR_RADII),
        "opacity_min_percent": MIN_OPACITY,
        "opacity_max_percent": MAX_OPACITY,
        "breathing_period_seconds": GLOW_PERIOD,
        "glow_nontransparent_pixels": sum(value > 0 for value in alpha_channel.get_flattened_data()),
        "glow_alpha_max": alpha_channel.getextrema()[1],
        "overlay_pixels_inside_button": nonzero_inside,
        "nearest_overlay_distance_outside_px": round(min_positive_distance, 4) if math.isfinite(min_positive_distance) else None,
    }
    if stats["overlay_pixels_inside_button"] != 0:
        raise AssertionError("The outer halo mask added pixels inside the button contour")
    if stats["glow_nontransparent_pixels"] == 0:
        raise AssertionError("The outer halo mask rendered empty")
    if stats["glow_alpha_max"] < 245:
        raise AssertionError("The layer opacity would understate the requested glow opacity range")
    return glow, stats


def opacity_at(seconds: float) -> float:
    phase = (seconds % GLOW_PERIOD) / GLOW_PERIOD
    return MIN_OPACITY + (MAX_OPACITY - MIN_OPACITY) * (1 - math.cos(2 * math.pi * phase)) / 2


def overlay_for_source(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def update_lottie(glow_png: bytes, phase52) -> tuple[dict, dict]:
    composition = json.loads(BASE_JSON.read_text(encoding="utf-8"))
    if (composition.get("w"), composition.get("h"), composition.get("fr"), composition.get("op")) != (W, H, 30, 270):
        raise AssertionError("Phase 5.2 composition dimensions or timeline changed")
    base_layers = {layer["nm"]: copy.deepcopy(layer) for layer in composition["layers"]}
    reflection_name = "portfolio-button-rounded-border-reflection"
    composition["layers"] = [layer for layer in composition["layers"]
                              if layer["nm"] != reflection_name]
    glow_layer = next(layer for layer in composition["layers"]
                      if layer["nm"] == "portfolio-button-ambient-glow-from-existing-border")
    glow_asset = next(asset for asset in composition["assets"]
                      if asset.get("id") == glow_layer["refId"])
    old_glow_layer = copy.deepcopy(glow_layer)
    old_glow_asset = copy.deepcopy(glow_asset)
    glow_asset["p"] = overlay_for_source(glow_png)
    glow_layer["nm"] = "portfolio-button-outer-halo-from-existing-rounded-border"
    glow_layer["ks"]["o"] = {
        "a": 1,
        "k": phase52.make_keyframes(phase52.glow_points(), "smooth"),
    }
    composition["nm"] = "Profile banner — Phase 5.3 outer-only portfolio button glow"
    checks = {
        "composition_size_and_timing_preserved": (composition["w"], composition["h"], composition["fr"], composition["op"]) == (W, H, 30, 270),
        "all_layers_except_glow_unchanged": all(
            layer == base_layers[layer["nm"]]
            for layer in composition["layers"]
            if layer["nm"] != "portfolio-button-outer-halo-from-existing-rounded-border"
        ),
        "preexisting_moving_border_reflection_removed_from_copy": all(layer["nm"] != reflection_name for layer in composition["layers"]),
        "original_banner_layer_unchanged": next(layer for layer in composition["layers"] if layer["nm"] == "unchanged original banner") == base_layers["unchanged original banner"],
        "source_border_layer_changed_only_by_opacity_and_name": all(
            glow_layer[key] == old_glow_layer[key]
            for key in old_glow_layer if key not in {"nm", "ks"}
        ) and glow_layer["ks"]["p"] == old_glow_layer["ks"]["p"] and glow_layer["ks"]["s"] == old_glow_layer["ks"]["s"] and glow_layer["ks"]["r"] == old_glow_layer["ks"]["r"],
        "glow_asset_embedded": glow_asset["p"].startswith("data:image/png;base64,"),
        "glow_asset_geometry_unchanged": (glow_asset["w"], glow_asset["h"], glow_asset["u"], glow_asset["e"]) == (old_glow_asset["w"], old_glow_asset["h"], old_glow_asset["u"], old_glow_asset["e"]),
    }
    if not all(checks.values()):
        raise AssertionError(f"Unexpected non-glow Lottie changes: {checks}")
    return composition, checks


def update_svg(glow_png: bytes) -> str:
    tree = ET.parse(BASE_SVG)
    root = tree.getroot()
    title = root.find(f"./{{{SVG_NS}}}title")
    description = root.find(f"./{{{SVG_NS}}}desc")
    if title is not None:
        title.text = "Cristian Barreiro profile banner — subtle outer glow around the existing portfolio-button border"
    if description is not None:
        description.text = "The original banner and button remain unchanged. A cyan-to-violet halo is derived from the existing rounded border and fades only outside its contour."
    old_reflection = root.find(f"./{{{SVG_NS}}}g[@id='portfolio-button-border-only']")
    if old_reflection is not None:
        root.remove(old_reflection)
    glow_image = root.find(f".//{{{SVG_NS}}}image[@id='portfolio-button-ambient-glow']")
    if glow_image is None:
        raise AssertionError("Could not find the existing portfolio glow SVG layer")
    glow_image.set("href", overlay_for_source(glow_png))
    glow_animation = glow_image.find(f"./{{{SVG_NS}}}animate")
    if glow_animation is None:
        raise AssertionError("Could not find the existing glow opacity animation")
    glow_animation.set("values", f"{MIN_OPACITY / 100:.3f};{MAX_OPACITY / 100:.3f};{MIN_OPACITY / 100:.3f}")
    glow_animation.set("dur", f"{GLOW_PERIOD:.1f}s")
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def render_frame(source: Image.Image, glow: Image.Image, repair: Image.Image,
                 cursor: Image.Image, phase52, seconds: float) -> Image.Image:
    frame = source.convert("RGBA")
    frame.alpha_composite(phase52.adjust_opacity(glow, opacity_at(seconds)), SOURCE_MASK_CROP[:2])
    # Preserve the terminal cursor and its background repair; omit the old moving border reflection.
    frame.alpha_composite(repair, phase52.CURSOR_PATCH[:2])
    frame.alpha_composite(phase52.adjust_opacity(cursor, phase52.cursor_opacity(seconds)), phase52.CURSOR_PATCH[:2])
    return frame


def save_apng(frames: list[Image.Image], destination: Path, duration_ms: float) -> None:
    """Save full-color APNG; Pillow stores changed rectangles as delta frames."""
    rgb_frames = [frame if frame.mode == "RGB" else frame.convert("RGB") for frame in frames]
    rgb_frames[0].save(
        destination,
        format="PNG",
        save_all=True,
        append_images=rgb_frames[1:],
        duration=duration_ms,
        loop=0,
        disposal=0,
        blend=0,
        optimize=True,
    )


def main() -> None:
    started = time.perf_counter()
    PREVIEW.mkdir(parents=True, exist_ok=True)
    LAYERS.mkdir(parents=True, exist_ok=True)
    phase52 = import_phase52()
    source_bytes = SOURCE.read_bytes()
    source = Image.open(io.BytesIO(source_bytes)).convert("RGB")
    if source.size != (W, H):
        raise AssertionError(f"Original artwork dimensions changed: {source.size}")

    glow, glow_stats = make_outer_halo(source, phase52)
    glow_path = LAYERS / "portfolio-button-outer-halo.png"
    glow.save(glow_path, optimize=True)
    glow_bytes = glow_path.read_bytes()
    composition, lottie_checks = update_lottie(glow_bytes, phase52)
    lottie_path = OUT / "profile-banner-phase-5.3.json"
    lottie_path.write_text(json.dumps(composition, separators=(",", ":")), encoding="utf-8")
    svg_path = OUT / "profile-banner-phase-5.3.svg"
    svg_path.write_text(update_svg(glow_bytes), encoding="utf-8")

    static_path = PREVIEW / "profile-banner-phase-5.3-static.png"
    shutil.copyfile(SOURCE, static_path)
    static_preview = source.resize(PREVIEW_SIZE, Image.Resampling.LANCZOS)
    frames = []
    cursor_core = phase52.cursor_core_box(source)
    repair_rgb, _repair_stats = phase52.make_cursor_repair(source, cursor_core)
    repair = repair_rgb.convert("RGBA")
    cursor = source.crop(phase52.CURSOR_PATCH).convert("RGBA")
    for index in range(PREVIEW_FRAMES):
        seconds = index / PREVIEW_FPS
        high_res = render_frame(source, glow, repair, cursor, phase52, seconds)
        scaled = high_res.resize(PREVIEW_SIZE, Image.Resampling.LANCZOS)
        frames.append(scaled.convert("RGB"))
    animated_path = PREVIEW / "profile-banner-phase-5.3.png"
    save_apng(frames, animated_path, 1000 / PREVIEW_FPS)
    detail_path = PREVIEW / "portfolio-button-outer-halo-detail-peak.png"
    detail = source.convert("RGBA")
    detail.alpha_composite(phase52.adjust_opacity(glow, MAX_OPACITY), SOURCE_MASK_CROP[:2])
    detail = detail.crop((990, 428, 1617, 624)).resize((1254, 392), Image.Resampling.LANCZOS)
    detail.convert("RGB").save(detail_path, optimize=True)

    # Compare the static image and every changed preview frame against source.
    if ImageChops.difference(Image.open(static_path).convert("RGB"), source).getbbox() is not None:
        raise AssertionError("The static preview differs from the immutable source artwork")
    if Image.open(static_path).size != (W, H):
        raise AssertionError("The static preview dimensions changed")

    full_min = source.convert("RGBA")
    full_min.alpha_composite(phase52.adjust_opacity(glow, MIN_OPACITY), SOURCE_MASK_CROP[:2])
    full_max = source.convert("RGBA")
    full_max.alpha_composite(phase52.adjust_opacity(glow, MAX_OPACITY), SOURCE_MASK_CROP[:2])
    button_roi = full_min.crop((990, 428, 1618, 624)).convert("RGB")
    peak_roi = full_max.crop((990, 428, 1618, 624)).convert("RGB")
    source_roi = source.crop((990, 428, 1618, 624))
    def metrics(image: Image.Image) -> tuple[int, int]:
        difference = ImageChops.difference(image, source_roi)
        count = sum(max(pixel) > 10 for pixel in difference.get_flattened_data())
        peak = max(channel[1] for channel in difference.getextrema())
        return count, peak
    trough_count, trough_peak = metrics(button_roi)
    peak_count, peak_peak = metrics(peak_roi)

    # Validate that the new halo itself has no alpha inside the rounded button.
    x0, y0 = SOURCE_MASK_CROP[:2]
    halo_alpha = glow.getchannel("A")
    alpha_pixels = halo_alpha.load()
    inside_alpha_pixels = 0
    for cy in range(glow.height):
        for cx in range(glow.width):
            if phase52._rounded_rect_distance(x0 + cx + 0.5, y0 + cy + 0.5) <= 0 and alpha_pixels[cx, cy] > 0:
                inside_alpha_pixels += 1
    if inside_alpha_pixels:
        raise AssertionError(f"The glow overlaps the button interior by {inside_alpha_pixels} pixels")

    # Every preview frame may differ only in the portfolio area or the original cursor.
    sx, sy = PREVIEW_SIZE[0] / W, PREVIEW_SIZE[1] / H
    button_box = tuple(round(value * (sx if index % 2 == 0 else sy))
                       for index, value in enumerate((985, 424, 1622, 629)))
    cursor_box = tuple(round(value * (sx if index % 2 == 0 else sy))
                       for index, value in enumerate((1138, 372, 1174, 401)))
    for frame in frames:
        changed = ImageChops.difference(frame, static_preview)
        outside = changed.copy()
        draw = ImageDraw.Draw(outside)
        draw.rectangle(button_box, fill=(0, 0, 0))
        draw.rectangle(cursor_box, fill=(0, 0, 0))
        if outside.getbbox() is not None:
            raise AssertionError("Preview animation changed pixels outside the button and cursor areas")

    with Image.open(animated_path) as animation:
        if animation.n_frames != PREVIEW_FRAMES:
            raise AssertionError(f"Expected {PREVIEW_FRAMES} preview frames, got {animation.n_frames}")
        elapsed = 0
        for frame_index in range(animation.n_frames):
            animation.seek(frame_index)
            elapsed += animation.info.get("duration", 0)
            if animation.size != PREVIEW_SIZE:
                raise AssertionError("Animated preview does not match README dimensions")
        if round(elapsed) != 9000:
            raise AssertionError(f"Expected a 9-second preview loop, got {elapsed} ms")

    preview_html = PREVIEW / "preview.html"
    preview_html.write_text(
        '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Phase 5.3 outer-only portfolio halo</title>'
        '<style>body{margin:0;padding:20px;background:#080a10;color:#eaf2ff;font:14px system-ui,sans-serif}'
        'main{max-width:1000px;margin:auto}img{display:block;width:100%;height:auto}p{color:#9cb4d8}</style>'
        '<main><img src="profile-banner-phase-5.3.png" alt="Original banner with a subtle breathing halo outside the rounded portfolio button border">'
        '<p>Full-color animated PNG preview at README display width. The original button interior and text remain untouched.</p>'
        '<p><a href="lottie-preview.html">Open the Lottie-Web composition</a></p></main>',
        encoding="utf-8",
    )
    lottie_html = PREVIEW / "lottie-preview.html"
    lottie_html.write_text(
        '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Phase 5.3 Lottie preview</title>'
        '<style>body{margin:0;padding:20px;background:#080a10;color:#eaf2ff;font:14px system-ui,sans-serif}'
        'main{max-width:1000px;margin:auto}#banner{width:100%;aspect-ratio:1672/941;background:#05070c}'
        '#status{margin-top:10px;color:#9cb4d8}</style>'
        '<main><div id="banner" role="img" aria-label="Full banner with outer-only portfolio button glow"></div>'
        '<p id="status">Loading the Phase 5.3 Lottie composition…</p></main>'
        '<script src="/node_modules/lottie-web/build/player/lottie.min.js"></script><script>'
        'const status=document.getElementById("status");const animation=bodymovin.loadAnimation({container:document.getElementById("banner"),'
        'renderer:"svg",loop:true,autoplay:true,path:"../profile-banner-phase-5.3.json",'
        'rendererSettings:{preserveAspectRatio:"xMidYMid meet"}});'
        'animation.addEventListener("DOMLoaded",()=>{status.textContent="Lottie-Web loaded; the outer-only breathing halo is active.";});'
        'animation.addEventListener("data_failed",()=>{status.textContent="Lottie JSON failed to load.";});</script>',
        encoding="utf-8",
    )

    # The three-second breathing cycle divides the existing nine-second loop exactly.
    if opacity_at(0) != opacity_at(9) or abs(opacity_at(3) - MIN_OPACITY) > 1e-8:
        raise AssertionError("Glow cycle does not close cleanly over the composition loop")
    if abs(opacity_at(1.5) - MAX_OPACITY) > 1e-8:
        raise AssertionError("Glow does not reach its intended opacity peak")

    svg_root = ET.parse(svg_path).getroot()
    if (svg_root.get("width"), svg_root.get("height"), svg_root.get("viewBox")) != (str(W), str(H), f"0 0 {W} {H}"):
        raise AssertionError("The SVG canvas or aspect ratio changed")
    if len(svg_root.findall(f".//{{{SVG_NS}}}animate")) < 2:
        raise AssertionError("The SVG is missing the glow or cursor animation")

    report = {
        "version": "5.3",
        "source_png_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "source_png_unchanged": True,
        "phase_5_2_json_sha256": hashlib.sha256(BASE_JSON.read_bytes()).hexdigest(),
        "phase_5_2_source_files_modified": False,
        "glow": glow_stats,
        "lottie_checks": lottie_checks,
        "dimensions": {"composition": [W, H], "readme_preview": list(PREVIEW_SIZE)},
        "button_fill_text_and_arrow_pixels_in_new_overlay": 0,
        "static_preview_pixel_identical_to_source": True,
        "animated_preview": {
        "file": "preview/profile-banner-phase-5.3.png",
            "frames": PREVIEW_FRAMES,
            "duration_seconds": 9,
            "format": "APNG, full-color PNG animation",
        "frame_rate_fps": PREVIEW_FPS,
            "glow_trough_changed_pixels_over_10": trough_count,
            "glow_trough_peak_channel_difference": trough_peak,
            "glow_peak_changed_pixels_over_10": peak_count,
            "glow_peak_peak_channel_difference": peak_peak,
        },
        "loop_closes_at_composition_end": True,
    }
    (OUT / "glow-refinement-validation-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    markdown = f"""# Phase 5.3 portfolio button glow refinement

## Change

- Created a separate copy of the current Phase 5.2 composition. The Phase 5.2 files and the original `assets/image.png` were not modified by this generator.
- Replaced the existing glow layer's transparent PNG and opacity curve. Omitted the prior separate moving border reflection from this copy to keep the button free of beams. The source button, border gradient, fill, text, arrow, dimensions, terminal cursor layers, and original background layer remain unchanged.
- The halo colors come from bright cyan-to-violet pixels selected from the existing rounded border. Gaussian blur softens those source pixels; a rounded-rectangle signed-distance mask clips every halo pixel to the outside of the button contour. No second outline or new geometry is drawn.
- Glow opacity breathes smoothly from {MIN_OPACITY:.0f}% to {MAX_OPACITY:.0f}% over {GLOW_PERIOD:.1f} seconds. The three-second cycle divides the existing nine-second composition exactly, so the loop closes without a jump.

## Validation

- Original image SHA-256: `{report['source_png_sha256']}`. The source and the source-identical static preview are both {W}×{H}.
- The halo source mask covers the four border sides: `{glow_stats['side_coverage_pixels']}`; rounded corners: `{glow_stats['rounded_corner_coverage_pixels']}`.
- Added overlay pixels inside the rounded button contour: **0**. This leaves the button fill, text, and arrow clean.
- The animated preview is {PREVIEW_SIZE[0]}×{PREVIEW_SIZE[1]}, matching the README display width. At the trough, {trough_count} pixels in the button detail region change by more than 10 channel levels; the peak maximum channel difference is {peak_peak}.
- Lottie validation confirms the original-background layer is unchanged; all retained layers match the Phase 5.2 source copy except the refined glow. The prior moving border-reflection layer is omitted only from this copy. The composition remains {W}×{H} at 30 fps for 9 seconds.
- The SVG keeps the same canvas and existing animation layers; only the glow image data and glow opacity cycle change.

## Deliverables

- `profile-banner-phase-5.3.json` — self-contained Lottie JSON.
- `profile-banner-phase-5.3.svg` — same-canvas animated SVG.
- `preview/profile-banner-phase-5.3.png` — full-color animated PNG at README display size, avoiding GIF palette artifacts.
- `preview/profile-banner-phase-5.3-static.png` — exact original artwork without animation.
- `preview/portfolio-button-outer-halo-detail-peak.png` — enlarged still of the halo at peak intensity.
- `layers/portfolio-button-outer-halo.png` — transparent, outside-only glow overlay.
"""
    (OUT / "glow-refinement-validation-report.md").write_text(markdown, encoding="utf-8")
    print(json.dumps({
        "lottie": str(lottie_path),
        "svg": str(svg_path),
        "preview": str(animated_path),
        "detail": str(detail_path),
        "report": str(OUT / "glow-refinement-validation-report.md"),
        "glow": glow_stats,
        "lottie_checks": lottie_checks,
        "preview_metrics": report["animated_preview"],
        "elapsed_seconds": round(time.perf_counter() - started, 1),
    }, indent=2))


if __name__ == "__main__":
    main()
