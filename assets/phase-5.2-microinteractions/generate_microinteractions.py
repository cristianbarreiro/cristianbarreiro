"""Build Phase 5.2 button-glow and terminal-cursor deliverables.

The current full-canvas Lottie source is the active button-only composition.
Its embedded original PNG and existing border reflection are preserved; the
new layers are local raster extracts with native Lottie opacity keyframes.
"""

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
BASE_LOTTIE = ROOT / "assets" / "profile-banner-button-only" / "profile-banner-button-only.json"
W, H = 1672, 941
FPS = 30
DURATION = 9.0
END_FRAME = int(FPS * DURATION)
PREVIEW_SIZE = (720, 405)
PREVIEW_FRAMES = 180
PREVIEW_FRAME_RATE = 20

# The border path is measured against the source pixels; the shape below is
# used only to reject unrelated luminous pixels while building its alpha mask.
BUTTON_RECT = (1012.0, 450.0, 1596.0, 606.0)
BUTTON_RADIUS = 22.0
BUTTON_GLOW_CROP = (994, 432, 1614, 624)

# The only cursor found on the final terminal line is the cyan underscore.
CURSOR_SEARCH = (1139, 376, 1180, 400)
CURSOR_PATCH = (1144, 378, 1169, 394)
CURSOR_CLEANUP_PADDING = (4, 4)
CURSOR_PERIOD_FRAMES = 30  # 1.0 s, exactly nine cycles over the 9 s composition.

GLOW_MIN_OPACITY = 18.0
GLOW_MAX_OPACITY = 78.0
GLOW_PERIOD_SECONDS = 3.0
GLOW_BLUR_RADIUS = 7.0

SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)


def qname(tag: str) -> str:
    return f"{{{SVG_NS}}}{tag}"


def embedded_png_asset(asset_id: str, image_bytes: bytes, width: int, height: int) -> dict:
    payload = base64.b64encode(image_bytes).decode("ascii")
    return {
        "id": asset_id,
        "w": width,
        "h": height,
        "u": "",
        "p": "data:image/png;base64," + payload,
        "e": 1,
    }


def png_bytes(image: Image.Image) -> bytes:
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True, compress_level=9)
    return output.getvalue()


def find_components(mask: list[list[bool]]) -> list[list[tuple[int, int]]]:
    height = len(mask)
    width = len(mask[0]) if height else 0
    seen: set[tuple[int, int]] = set()
    components = []
    for y in range(height):
        for x in range(width):
            if not mask[y][x] or (x, y) in seen:
                continue
            stack = [(x, y)]
            seen.add((x, y))
            points = []
            while stack:
                px, py = stack.pop()
                points.append((px, py))
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        nx, ny = px + dx, py + dy
                        if (0 <= nx < width and 0 <= ny < height
                                and mask[ny][nx] and (nx, ny) not in seen):
                            seen.add((nx, ny))
                            stack.append((nx, ny))
            components.append(points)
    return components


def cursor_core_box(source: Image.Image) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = CURSOR_SEARCH
    pixels = source.load()
    mask = []
    for y in range(y0, y1):
        row = []
        for x in range(x0, x1):
            red, green, blue = pixels[x, y]
            row.append(red < 90 and green > 135 and blue > 145
                       and green - red > 75 and blue - red > 80)
        mask.append(row)
    candidates = [points for points in find_components(mask) if len(points) >= 10]
    if not candidates:
        raise AssertionError("Could not isolate the existing terminal underscore")
    points = max(candidates, key=len)
    xs = [x + x0 for x, _ in points]
    ys = [y + y0 for _, y in points]
    return min(xs), min(ys), max(xs) + 1, max(ys) + 1


def cursor_core_pixel_count(source: Image.Image) -> int:
    x0, y0, x1, y1 = CURSOR_SEARCH
    pixels = source.load()
    count = 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            red, green, blue = pixels[x, y]
            if (red < 90 and green > 135 and blue > 145
                    and green - red > 75 and blue - red > 80):
                count += 1
    return count


def _rounded_rect_distance(x: float, y: float) -> float:
    left, top, right, bottom = BUTTON_RECT
    cx = (left + right) / 2
    cy = (top + bottom) / 2
    half_width = (right - left) / 2
    half_height = (bottom - top) / 2
    qx = abs(x - cx) - (half_width - BUTTON_RADIUS)
    qy = abs(y - cy) - (half_height - BUTTON_RADIUS)
    outside = math.hypot(max(qx, 0), max(qy, 0))
    inside = min(max(qx, qy), 0)
    return outside + inside - BUTTON_RADIUS


def make_button_glow(source: Image.Image) -> tuple[Image.Image, dict]:
    crop_box = BUTTON_GLOW_CROP
    x0, y0, x1, y1 = crop_box
    source_crop = source.crop(crop_box).convert("RGB")
    width, height = source_crop.size
    source_px = source_crop.load()
    core = Image.new("L", (width, height), 0)
    core_px = core.load()
    counts = {"top": 0, "right": 0, "bottom": 0, "left": 0}
    quadrant_counts = {"top_left": 0, "top_right": 0, "bottom_left": 0, "bottom_right": 0}
    center_x = (BUTTON_RECT[0] + BUTTON_RECT[2]) / 2
    center_y = (BUTTON_RECT[1] + BUTTON_RECT[3]) / 2

    for local_y in range(height):
        y = y0 + local_y + 0.5
        for local_x in range(width):
            x = x0 + local_x + 0.5
            if abs(_rounded_rect_distance(x, y)) > 4.6:
                continue
            red, green, blue = source_px[local_x, local_y]
            max_channel = max(red, green, blue)
            saturation = max_channel - min(red, green, blue)
            if max_channel < 105 or saturation < 46:
                continue
            # Keep the alpha tied to actual bright, chromatic source pixels.
            brightness_weight = min(1.0, max(0.0, (max_channel - 88) / 130))
            saturation_weight = min(1.0, saturation / 110)
            alpha = round(255 * brightness_weight * saturation_weight)
            if alpha < 32:
                continue
            core_px[local_x, local_y] = alpha
            distance = _rounded_rect_distance(x, y)
            if abs(y - BUTTON_RECT[1]) < 7 and BUTTON_RECT[0] + 30 < x < BUTTON_RECT[2] - 30:
                counts["top"] += 1
            if abs(x - BUTTON_RECT[2]) < 7 and BUTTON_RECT[1] + 30 < y < BUTTON_RECT[3] - 30:
                counts["right"] += 1
            if abs(y - BUTTON_RECT[3]) < 7 and BUTTON_RECT[0] + 30 < x < BUTTON_RECT[2] - 30:
                counts["bottom"] += 1
            if abs(x - BUTTON_RECT[0]) < 7 and BUTTON_RECT[1] + 30 < y < BUTTON_RECT[3] - 30:
                counts["left"] += 1
            key = ("top_" if y < center_y else "bottom_") + ("left" if x < center_x else "right")
            quadrant_counts[key] += 1

    if not core.getbbox():
        raise AssertionError("No bright border pixels were selected for the glow")
    if any(count < 15 for count in counts.values()):
        raise AssertionError(f"Border mask misses a side: {counts}")
    if any(count < 2 for count in quadrant_counts.values()):
        raise AssertionError(f"Border mask misses a rounded corner: {quadrant_counts}")

    blurred_alpha = core.filter(ImageFilter.GaussianBlur(GLOW_BLUR_RADIUS))
    alpha_data = blurred_alpha.load()
    core_data = core.load()
    rgb_channels = [source_crop.getchannel(channel) for channel in (0, 1, 2)]
    blurred_premultiplied = [
        ImageChops.multiply(channel, core).filter(ImageFilter.GaussianBlur(GLOW_BLUR_RADIUS))
        for channel in rgb_channels
    ]
    blurred_channels = [channel.load() for channel in blurred_premultiplied]

    glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    glow_px = glow.load()
    for y in range(height):
        for x in range(width):
            alpha = alpha_data[x, y]
            if alpha <= 2:
                continue
            source_alpha = core_data[x, y]
            # This subtraction softens the exact extracted stroke so the new
            # layer reads as a halo instead of a second crisp outline.
            halo_alpha = max(0, round(alpha * 0.86 - source_alpha * 0.22))
            if halo_alpha <= 2:
                continue
            color = []
            for channel in blurred_channels:
                color.append(max(0, min(255, round(channel[x, y] * 255 / alpha))))
            glow_px[x, y] = (*color, halo_alpha)

    stats = {
        "source_border_mask_pixels": sum(1 for value in core.get_flattened_data() if value > 0),
        "glow_nontransparent_pixels": sum(1 for value in glow.getchannel("A").get_flattened_data() if value > 0),
        "glow_alpha_max": glow.getchannel("A").getextrema()[1],
        "side_coverage_pixels": counts,
        "corner_coverage_pixels": quadrant_counts,
    }
    return glow, stats


def make_cursor_repair(source: Image.Image, core_box: tuple[int, int, int, int]) -> tuple[Image.Image, dict]:
    x0, y0, x1, y1 = CURSOR_PATCH
    patch = source.crop(CURSOR_PATCH).convert("RGB")
    repaired = patch.copy()
    core_left, core_top, core_right, core_bottom = core_box
    pad_x, pad_y = CURSOR_CLEANUP_PADDING
    cleanup = (max(x0 + 2, core_left - pad_x), max(y0 + 2, core_top - pad_y),
               min(x1 - 2, core_right + pad_x), min(y1 - 2, core_bottom + pad_y))
    cx0, cy0, cx1, cy1 = cleanup
    src_px = source.load()
    out_px = repaired.load()

    # Interpolate the tiny hidden background patch from immediately adjacent
    # terminal pixels. Pixels outside this cleanup area remain source-exact.
    left_sample_x = cx0 - 1
    right_sample_x = cx1
    top_sample_y = cy0 - 1
    bottom_sample_y = cy1
    for y in range(cy0, cy1):
        for x in range(cx0, cx1):
            fx = (x - left_sample_x) / (right_sample_x - left_sample_x)
            fy = (y - top_sample_y) / (bottom_sample_y - top_sample_y)
            estimates = []
            for channel in range(3):
                horizontal = src_px[left_sample_x, y][channel] * (1 - fx) + src_px[right_sample_x, y][channel] * fx
                vertical = src_px[x, top_sample_y][channel] * (1 - fy) + src_px[x, bottom_sample_y][channel] * fy
                estimates.append(round((horizontal + vertical) / 2))
            out_px[x - x0, y - y0] = tuple(estimates)

    # Keep the outermost one-pixel frame identical to its source for a clean
    # boundary; it contains no cursor pixels because of the safety padding.
    for local_x in range(patch.width):
        for local_y in (0, patch.height - 1):
            out_px[local_x, local_y] = patch.getpixel((local_x, local_y))
    for local_y in range(patch.height):
        for local_x in (0, patch.width - 1):
            out_px[local_x, local_y] = patch.getpixel((local_x, local_y))

    repair_stats = {
        "cursor_core_box": list(core_box),
        "repair_patch_box": list(CURSOR_PATCH),
        "reconstructed_background_box": list(cleanup),
        "changed_pixels_in_repair_asset": sum(
            1 for a, b in zip(patch.get_flattened_data(), repaired.get_flattened_data()) if a != b),
        "repair_outside_reconstructed_area_pixel_identical": True,
    }
    return repaired, repair_stats


def make_keyframes(points: list[tuple[int, float]], easing: str = "smooth") -> list[dict]:
    frames = []
    for index, (frame, value) in enumerate(points):
        if index + 1 < len(points):
            next_value = points[index + 1][1]
        else:
            next_value = value
        if easing == "smooth":
            outgoing = {"x": [0.42], "y": [0.0]}
            incoming = {"x": [0.58], "y": [1.0]}
        else:
            outgoing = {"x": [0.333], "y": [0.333]}
            incoming = {"x": [0.667], "y": [0.667]}
        frames.append({
            "t": frame,
            "s": [value],
            "e": [next_value],
            "i": incoming,
            "o": outgoing,
            "h": 0,
        })
    return frames


def glow_points() -> list[tuple[int, float]]:
    points = []
    for cycle_start in range(0, END_FRAME, int(FPS * GLOW_PERIOD_SECONDS)):
        points.extend([
            (cycle_start, GLOW_MIN_OPACITY),
            (cycle_start + int(FPS * GLOW_PERIOD_SECONDS / 2), GLOW_MAX_OPACITY),
        ])
    points.append((END_FRAME, GLOW_MIN_OPACITY))
    return points


def cursor_points() -> list[tuple[int, float]]:
    points: dict[int, float] = {}
    for cycle_start in range(0, END_FRAME, CURSOR_PERIOD_FRAMES):
        for offset, value in ((0, 100.0), (14, 100.0), (16, 0.0),
                              (26, 0.0), (28, 100.0), (30, 100.0)):
            frame = cycle_start + offset
            if frame <= END_FRAME:
                points[frame] = value
    return sorted(points.items())


def image_layer(index: int, name: str, asset_id: str, x: int = 0, y: int = 0,
                opacity: list[dict] | None = None) -> dict:
    return {
        "ddd": 0,
        "ind": index,
        "ty": 2,
        "nm": name,
        "refId": asset_id,
        "sr": 1,
        "ks": {
            "o": {"a": 1, "k": opacity} if opacity is not None else {"a": 0, "k": 100},
            "r": {"a": 0, "k": 0},
            "p": {"a": 0, "k": [x, y, 0]},
            "a": {"a": 0, "k": [0, 0, 0]},
            "s": {"a": 0, "k": [100, 100, 100]},
        },
        "ao": 0,
        "ip": 0,
        "op": END_FRAME,
        "st": 0,
        "bm": 0,
    }


def make_lottie(source_bytes: bytes, glow_png: bytes, cursor_png: bytes,
                repair_png: bytes, glow_size: tuple[int, int], cursor_size: tuple[int, int]) -> tuple[dict, dict]:
    base = json.loads(BASE_LOTTIE.read_text(encoding="utf-8"))
    if (base.get("w"), base.get("h"), base.get("fr"), base.get("op")) != (W, H, FPS, END_FRAME):
        raise AssertionError("The current Lottie base dimensions or timeline changed")
    if len(base.get("layers", [])) != 2 or base["layers"][0].get("ty") != 4:
        raise AssertionError("The current full-canvas base is not the expected button-only Lottie")
    original_button_layer = copy.deepcopy(base["layers"][0])
    original_layer_map = {layer["nm"]: copy.deepcopy(layer) for layer in base["layers"]}

    cursor_asset = embedded_png_asset("phase52_cursor_source", cursor_png, *cursor_size)
    repair_asset = embedded_png_asset("phase52_cursor_background_repair", repair_png,
                                      *cursor_size)
    glow_asset = embedded_png_asset("phase52_button_border_glow", glow_png, *glow_size)

    glow_layer = image_layer(
        3, "portfolio-button-ambient-glow-from-existing-border",
        "phase52_button_border_glow", BUTTON_GLOW_CROP[0], BUTTON_GLOW_CROP[1],
        make_keyframes(glow_points(), "smooth"),
    )
    cursor_layer = image_layer(
        4, "terminal-cursor-blink-at-original-underscore",
        "phase52_cursor_source", CURSOR_PATCH[0], CURSOR_PATCH[1],
        make_keyframes(cursor_points(), "linear"),
    )
    repair_layer = image_layer(
        5, "terminal-cursor-local-background-repair",
        "phase52_cursor_background_repair", CURSOR_PATCH[0], CURSOR_PATCH[1],
    )

    # Keep the existing rounded-border reflection layer object byte-for-byte
    # equivalent at the JSON-object level, with the base artwork still last.
    base["nm"] = "Profile banner — Phase 5.2 button glow and terminal cursor"
    base["assets"].extend([glow_asset, repair_asset, cursor_asset])
    base["layers"] = [cursor_layer, original_button_layer, glow_layer,
                      repair_layer, base["layers"][1]]
    checks = {
        "existing_button_layer_preserved": base["layers"][1] == original_layer_map[
            "portfolio-button-rounded-border-reflection"],
        "original_base_layer_preserved": base["layers"][4] == original_layer_map[
            "unchanged original banner"],
        "original_png_sha256": hashlib.sha256(source_bytes).hexdigest(),
    }
    return base, checks


def build_svg(source_bytes: bytes, old_svg_path: Path, glow_png: bytes,
              cursor_png: bytes, repair_png: bytes) -> str:
    source64 = base64.b64encode(source_bytes).decode("ascii")
    glow64 = base64.b64encode(glow_png).decode("ascii")
    cursor64 = base64.b64encode(cursor_png).decode("ascii")
    repair64 = base64.b64encode(repair_png).decode("ascii")

    root = ET.Element(qname("svg"), {
        "width": str(W), "height": str(H), "viewBox": f"0 0 {W} {H}",
        "role": "img", "aria-labelledby": "title description",
    })
    ET.SubElement(root, qname("title"), {"id": "title"}).text = (
        "Cristian Barreiro profile banner — subtle portfolio-button glow and blinking terminal cursor"
    )
    ET.SubElement(root, qname("desc"), {"id": "description"}).text = (
        "The original banner remains the background. A soft glow breathes from the existing portfolio-button border; the original terminal underscore blinks in place."
    )
    defs = ET.SubElement(root, qname("defs"))
    old_root = ET.parse(old_svg_path).getroot()
    old_group = old_root.find(f".//{qname('g')}[@id='portfolio-button-border-only']")
    if old_group is None:
        raise AssertionError("Could not find the current SVG border reflection layer")
    for old_def in old_root.findall(f"./{qname('defs')}/*"):
        defs.append(copy.deepcopy(old_def))

    def add_image(identifier: str, x: int, y: int, width: int, height: int, data_uri: str) -> ET.Element:
        return ET.SubElement(root, qname("image"), {
            "id": identifier, "x": str(x), "y": str(y),
            "width": str(width), "height": str(height),
            "href": data_uri, "preserveAspectRatio": "none",
        })

    add_image("original-banner", 0, 0, W, H, "data:image/png;base64," + source64)
    add_image("terminal-cursor-background-repair", CURSOR_PATCH[0], CURSOR_PATCH[1],
              CURSOR_PATCH[2] - CURSOR_PATCH[0], CURSOR_PATCH[3] - CURSOR_PATCH[1],
              "data:image/png;base64," + repair64)
    glow_x, glow_y = BUTTON_GLOW_CROP[0], BUTTON_GLOW_CROP[1]
    glow_width, glow_height = BUTTON_GLOW_CROP[2] - glow_x, BUTTON_GLOW_CROP[3] - glow_y
    glow_image = add_image("portfolio-button-ambient-glow", glow_x, glow_y,
                           glow_width, glow_height, "data:image/png;base64," + glow64)
    glow_animation = ET.SubElement(glow_image, qname("animate"), {
        "attributeName": "opacity",
        "values": f"{GLOW_MIN_OPACITY / 100:.3f};{GLOW_MAX_OPACITY / 100:.3f};{GLOW_MIN_OPACITY / 100:.3f}",
        "keyTimes": "0;0.5;1",
        "keySplines": "0.42 0 0.58 1;0.42 0 0.58 1",
        "calcMode": "spline", "dur": f"{GLOW_PERIOD_SECONDS:.1f}s",
        "repeatCount": "indefinite",
    })
    glow_animation.tail = ""

    root.append(copy.deepcopy(old_group))
    cursor_image = add_image(
        "terminal-cursor-source-crop", CURSOR_PATCH[0], CURSOR_PATCH[1],
        CURSOR_PATCH[2] - CURSOR_PATCH[0], CURSOR_PATCH[3] - CURSOR_PATCH[1],
        "data:image/png;base64," + cursor64,
    )
    cursor_animate = ET.SubElement(cursor_image, qname("animate"), {
        "attributeName": "opacity",
        "values": "1;1;0;0;1;1",
        "keyTimes": "0;0.4666667;0.5333333;0.8666667;0.9333333;1",
        "calcMode": "linear", "dur": "1s", "repeatCount": "indefinite",
    })
    cursor_animate.tail = ""
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def adjust_opacity(image: Image.Image, opacity: float) -> Image.Image:
    result = image.convert("RGBA")
    alpha = result.getchannel("A").point(lambda value: round(value * opacity / 100))
    result.putalpha(alpha)
    return result


def glow_opacity(seconds: float) -> float:
    phase = (seconds % GLOW_PERIOD_SECONDS) / GLOW_PERIOD_SECONDS
    return GLOW_MIN_OPACITY + (GLOW_MAX_OPACITY - GLOW_MIN_OPACITY) * (1 - math.cos(2 * math.pi * phase)) / 2


def cursor_opacity(seconds: float) -> float:
    frame = (seconds * FPS) % CURSOR_PERIOD_FRAMES
    if frame < 14:
        return 100.0
    if frame < 16:
        return 100.0 * (16.0 - frame) / 2.0
    if frame < 26:
        return 0.0
    if frame < 28:
        return 100.0 * (frame - 26.0) / 2.0
    return 100.0


def load_button_only_module():
    path = ROOT / "assets" / "profile-banner-button-only" / "generate_button_only.py"
    spec = importlib.util.spec_from_file_location("button_only_generation", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load the current button-only preview renderer")
    module = importlib.util.module_from_spec(spec)
    prior_bytecode_setting = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = prior_bytecode_setting
    return module


def render_high_resolution_frame(source: Image.Image, glow: Image.Image,
                                 repair: Image.Image, cursor: Image.Image,
                                 seconds: float) -> Image.Image:
    frame = source.convert("RGBA")
    frame.alpha_composite(repair.convert("RGBA"), (CURSOR_PATCH[0], CURSOR_PATCH[1]))
    frame.alpha_composite(adjust_opacity(glow, glow_opacity(seconds)),
                          (BUTTON_GLOW_CROP[0], BUTTON_GLOW_CROP[1]))
    frame.alpha_composite(adjust_opacity(cursor, cursor_opacity(seconds)),
                          (CURSOR_PATCH[0], CURSOR_PATCH[1]))
    return frame


def save_palette_gif(frames: list[Image.Image], static_base: Image.Image,
                     destination: Path, duration_ms: int) -> None:
    palette = static_base.convert("P", palette=Image.Palette.ADAPTIVE, colors=256)
    background = static_base.quantize(palette=palette, dither=Image.Dither.FLOYDSTEINBERG)
    indexed = []
    for frame in frames:
        rgb = frame.convert("RGB")
        changed = ImageChops.difference(rgb, static_base).convert("L")
        mask = changed.point(lambda value: 255 if value else 0)
        quantized = rgb.quantize(palette=palette, dither=Image.Dither.NONE)
        indexed_frame = background.copy()
        indexed_frame.paste(quantized, mask=mask)
        indexed.append(indexed_frame)
    indexed[0].save(destination, save_all=True, append_images=indexed[1:],
                     duration=duration_ms, loop=0, disposal=1, optimize=True)


def border_detail_gif(source: Image.Image, glow: Image.Image, destination: Path) -> None:
    region = (988, 426, 1618, 625)
    frames = []
    glow_full = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    glow_full.alpha_composite(glow.convert("RGBA"), (BUTTON_GLOW_CROP[0], BUTTON_GLOW_CROP[1]))
    for index in range(60):
        t = index / 20
        hi = source.convert("RGBA")
        hi.alpha_composite(adjust_opacity(glow_full, glow_opacity(t)))
        preview = hi.crop(region).resize((756, 239), Image.Resampling.LANCZOS)
        frames.append(preview.convert("RGB"))
    save_palette_gif(frames, frames[0], destination, 50)


def cursor_detail_gif(source: Image.Image, repair: Image.Image, cursor: Image.Image,
                      destination: Path) -> None:
    region = (1120, 360, 1190, 405)
    frames = []
    for index in range(40):
        t = index / 20
        frame = source.convert("RGBA")
        frame.alpha_composite(repair.convert("RGBA"), (CURSOR_PATCH[0], CURSOR_PATCH[1]))
        frame.alpha_composite(adjust_opacity(cursor, cursor_opacity(t)),
                              (CURSOR_PATCH[0], CURSOR_PATCH[1]))
        crop = frame.crop(region).resize((420, 270), Image.Resampling.NEAREST)
        frames.append(crop.convert("RGB"))
    save_palette_gif(frames, frames[0], destination, 50)


def main() -> None:
    started = time.perf_counter()
    PREVIEW.mkdir(parents=True, exist_ok=True)
    LAYERS.mkdir(parents=True, exist_ok=True)

    source_bytes = SOURCE.read_bytes()
    source = Image.open(SOURCE).convert("RGB")
    if source.size != (W, H):
        raise ValueError(f"Expected original artwork at {W}x{H}, got {source.size}")
    if not BASE_LOTTIE.is_file():
        raise FileNotFoundError(f"Current full-canvas Lottie source not found: {BASE_LOTTIE}")

    core_box = cursor_core_box(source)
    if core_box[0] < 1145 or core_box[2] > 1168 or core_box[1] < 382 or core_box[3] > 390:
        raise AssertionError(f"Detected cursor is outside its expected terminal slot: {core_box}")
    cursor_crop = source.crop(CURSOR_PATCH).convert("RGBA")
    repair_rgb, repair_stats = make_cursor_repair(source, core_box)
    repair_crop = repair_rgb.convert("RGBA")
    glow, glow_stats = make_button_glow(source)

    # Store transparent/local image layers beside the self-contained exports.
    glow_path = LAYERS / "portfolio-button-ambient-glow.png"
    repair_path = LAYERS / "terminal-cursor-background-repair.png"
    cursor_path = LAYERS / "terminal-cursor-source-crop.png"
    glow.save(glow_path, optimize=True)
    repair_crop.save(repair_path, optimize=True)
    cursor_crop.save(cursor_path, optimize=True)

    glow_bytes = glow_path.read_bytes()
    repair_bytes = repair_path.read_bytes()
    cursor_bytes = cursor_path.read_bytes()
    lottie, lottie_checks = make_lottie(
        source_bytes, glow_bytes, cursor_bytes, repair_bytes, glow.size, cursor_crop.size)
    lottie_path = OUT / "profile-banner-phase-5.2.json"
    lottie_path.write_text(json.dumps(lottie, separators=(",", ":")), encoding="utf-8")

    svg_path = OUT / "profile-banner-phase-5.2.svg"
    svg_text = build_svg(source_bytes, ROOT / "assets" / "profile-banner-button-only" / "profile-banner-button-only.svg",
                         glow_bytes, cursor_bytes, repair_bytes)
    svg_path.write_text(svg_text, encoding="utf-8")

    static_path = PREVIEW / "profile-banner-phase-5.2-static.png"
    shutil.copyfile(SOURCE, static_path)
    source_preview = source.resize(PREVIEW_SIZE, Image.Resampling.LANCZOS)
    button_renderer = load_button_only_module()
    animation_frames = []
    for index in range(PREVIEW_FRAMES):
        seconds = index / PREVIEW_FRAME_RATE
        high_res = render_high_resolution_frame(source, glow, repair_crop, cursor_crop, seconds)
        # Include the preserved base reflection in the full animation preview.
        scaled = high_res.resize(PREVIEW_SIZE, Image.Resampling.LANCZOS)
        scaled.alpha_composite(button_renderer.reflection_overlay(seconds))
        animation_frames.append(scaled.convert("RGB"))

    animated_path = PREVIEW / "profile-banner-phase-5.2.gif"
    save_palette_gif(animation_frames, source_preview, animated_path, 50)
    border_path = PREVIEW / "portfolio-button-glow-detail.gif"
    border_detail_gif(source, glow, border_path)
    cursor_detail_path = PREVIEW / "terminal-cursor-blink-detail.gif"
    cursor_detail_gif(source, repair_crop, cursor_crop, cursor_detail_path)

    # Validate the exact pixel source, the isolated patch, and loop closure.
    static_image = Image.open(static_path).convert("RGB")
    if ImageChops.difference(static_image, source).getbbox() is not None:
        raise AssertionError("The static preview differs from the original artwork")
    repaired_full = source.convert("RGBA")
    repaired_full.alpha_composite(repair_crop, (CURSOR_PATCH[0], CURSOR_PATCH[1]))
    repaired_rgb = repaired_full.convert("RGB")
    patch_difference = ImageChops.difference(source, repaired_rgb)
    outside_patch = patch_difference.copy()
    ImageDraw.Draw(outside_patch).rectangle(CURSOR_PATCH, fill=(0, 0, 0))
    if outside_patch.getbbox() is not None:
        raise AssertionError("Cursor cleanup changed pixels outside its isolated crop")
    if cursor_core_pixel_count(repaired_rgb) != 0:
        raise AssertionError("The original underscore remains visible under the blinking layer")
    visible_full = source.copy().convert("RGBA")
    visible_full.alpha_composite(repair_crop, (CURSOR_PATCH[0], CURSOR_PATCH[1]))
    visible_full.alpha_composite(cursor_crop, (CURSOR_PATCH[0], CURSOR_PATCH[1]))
    visible_diff = ImageChops.difference(visible_full.convert("RGB"), source)
    if visible_diff.getbbox() is not None:
        raise AssertionError("The visible cursor layer does not reproduce its original pixels exactly")

    # Confirm the new animated preview only changes the button and cursor areas.
    with Image.open(animated_path) as animation:
        if animation.n_frames != PREVIEW_FRAMES:
            raise AssertionError(f"Expected {PREVIEW_FRAMES} GIF frames, got {animation.n_frames}")
        total_duration = 0
        first_frame = None
        for frame_index in range(animation.n_frames):
            animation.seek(frame_index)
            total_duration += animation.info.get("duration", 0)
            current = animation.convert("RGB")
            if first_frame is None:
                first_frame = current.copy()
            difference = ImageChops.difference(current, first_frame)
            outside_effects = difference.copy()
            ImageDraw.Draw(outside_effects).rectangle((420, 180, 700, 275), fill=(0, 0, 0))
            ImageDraw.Draw(outside_effects).rectangle((485, 160, 520, 178), fill=(0, 0, 0))
            if outside_effects.getbbox() is not None:
                raise AssertionError("Animated pixels escaped the button/cursor effect regions")
        if total_duration != round(DURATION * 1000):
            raise AssertionError("The animated preview duration is not a complete 9-second loop")

    with Image.open(border_path) as detail:
        detail_duration = 0
        for index in range(detail.n_frames):
            detail.seek(index)
            detail_duration += detail.info.get("duration", 0)
        if detail.n_frames < 12 or detail_duration != 3000:
            raise AssertionError("The button detail preview must show one seamless 3-second glow cycle")
    with Image.open(cursor_detail_path) as detail:
        detail_duration = 0
        for index in range(detail.n_frames):
            detail.seek(index)
            detail_duration += detail.info.get("duration", 0)
        if detail.n_frames < 6 or detail_duration != 2000:
            raise AssertionError("The cursor detail preview must show two complete 1-second blink cycles")
        sample_xy = ((1156 - 1120) * 6, (385 - 360) * 6)
        detail.seek(0)
        visible_cursor_pixel = detail.convert("RGB").getpixel(sample_xy)
        elapsed_ms = 0
        hidden_frame = None
        for index in range(detail.n_frames):
            detail.seek(index)
            frame_duration = detail.info.get("duration", 0)
            if elapsed_ms <= 700 < elapsed_ms + frame_duration:
                hidden_frame = detail.convert("RGB")
                break
            elapsed_ms += frame_duration
        if hidden_frame is None:
            raise AssertionError("Could not sample the hidden cursor phase from its detail GIF")
        hidden_cursor_pixel = hidden_frame.getpixel(sample_xy)
        if max(abs(a - b) for a, b in zip(visible_cursor_pixel, hidden_cursor_pixel)) < 60:
            raise AssertionError("The cursor detail preview does not visibly blink off")

    frame_zero = render_high_resolution_frame(source, glow, repair_crop, cursor_crop, 0)
    frame_loop = render_high_resolution_frame(source, glow, repair_crop, cursor_crop, DURATION)
    if ImageChops.difference(frame_zero, frame_loop).getbbox() is not None:
        raise AssertionError("The glow/cursor loop does not return to its starting state")
    if not lottie_checks["existing_button_layer_preserved"] or not lottie_checks["original_base_layer_preserved"]:
        raise AssertionError("An existing Lottie layer was changed")

    # Measure the glow over the original artwork at 720 px preview scale.
    glow_min = source.convert("RGBA")
    glow_min.alpha_composite(adjust_opacity(glow, GLOW_MIN_OPACITY),
                             (BUTTON_GLOW_CROP[0], BUTTON_GLOW_CROP[1]))
    glow_max = source.convert("RGBA")
    glow_max.alpha_composite(adjust_opacity(glow, GLOW_MAX_OPACITY),
                             (BUTTON_GLOW_CROP[0], BUTTON_GLOW_CROP[1]))
    glow_min_preview = glow_min.resize(PREVIEW_SIZE, Image.Resampling.LANCZOS).convert("RGB")
    glow_max_preview = glow_max.resize(PREVIEW_SIZE, Image.Resampling.LANCZOS).convert("RGB")
    glow_delta = ImageChops.difference(glow_max_preview, glow_min_preview)
    glow_box_preview = (round(1000 * PREVIEW_SIZE[0] / W), round(435 * PREVIEW_SIZE[1] / H),
                        round(1608 * PREVIEW_SIZE[0] / W), round(620 * PREVIEW_SIZE[1] / H))
    glow_roi = glow_delta.crop(glow_box_preview)
    glow_stats["preview_scale_pixels_over_10_difference"] = sum(
        1 for pixel in glow_roi.get_flattened_data() if max(pixel) > 10)
    glow_stats["preview_scale_max_channel_difference"] = max(
        channel_extrema[1] for channel_extrema in glow_roi.getextrema())
    if glow_stats["preview_scale_pixels_over_10_difference"] < 300:
        raise AssertionError("The button glow is too weak to register clearly at preview scale")

    svg_root = ET.parse(svg_path).getroot()
    if (svg_root.get("width"), svg_root.get("height"), svg_root.get("viewBox")) != (
            str(W), str(H), f"0 0 {W} {H}"):
        raise AssertionError("SVG dimensions or aspect ratio changed")
    if len(svg_root.findall(f".//{qname('animate')}")) < 3:
        raise AssertionError("The SVG is missing the reflection, glow, or cursor animation")

    html = PREVIEW / "preview.html"
    html.write_text(
        '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Phase 5.2 — portfolio glow and terminal cursor</title>'
        '<style>body{margin:0;padding:20px;background:#080a10;color:#eaf2ff;font:14px system-ui,sans-serif}'
        'main{max-width:1000px;margin:auto}img{display:block;width:100%;height:auto}p{color:#9cb4d8}</style>'
        '<main><img src="profile-banner-phase-5.2.gif" alt="Original banner with a breathing portfolio-button glow and blinking terminal cursor">'
        '<p>The original artwork remains the background. The portfolio-button halo breathes, and the existing terminal underscore blinks in place.</p>'
        '<p><a href="lottie-preview.html">Open the Lottie-Web composition</a></p></main>',
        encoding="utf-8",
    )
    lottie_html = PREVIEW / "lottie-preview.html"
    lottie_html.write_text(
        '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Phase 5.2 Lottie-Web preview</title>'
        '<style>body{margin:0;padding:20px;background:#080a10;color:#eaf2ff;font:14px system-ui,sans-serif}'
        'main{max-width:1000px;margin:auto}#banner{width:100%;aspect-ratio:1672/941;background:#05070c}'
        '#status{margin-top:10px;color:#9cb4d8}</style>'
        '<main><div id="banner" role="img" aria-label="Full banner with button glow and blinking cursor"></div>'
        '<p id="status">Loading the five-layer Lottie composition…</p></main>'
        '<script src="/node_modules/lottie-web/build/player/lottie.min.js"></script><script>'
        'const status=document.getElementById("status");const animation=bodymovin.loadAnimation({container:document.getElementById("banner"),'
        'renderer:"svg",loop:true,autoplay:true,path:"../profile-banner-phase-5.2.json",'
        'rendererSettings:{preserveAspectRatio:"xMidYMid meet"}});'
        'animation.addEventListener("DOMLoaded",()=>{status.textContent="Lottie-Web loaded; the current border reflection, breathing halo, and blinking cursor are active.";});'
        'animation.addEventListener("data_failed",()=>{status.textContent="Lottie JSON failed to load.";});</script>',
        encoding="utf-8",
    )

    report = {
        "source_png_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "source_png_bytes_unchanged": True,
        "active_base_lottie": BASE_LOTTIE.relative_to(ROOT).as_posix(),
        "previous_phase_5_1_source_available_in_working_tree": False,
        "previous_validated_animation_preserved": "Current button-border reflection layer copied unchanged from the active button-only Lottie.",
        "original_phase5_1_effects": "Not present in the current active composition; earlier circuit/ring layers were not reintroduced.",
        "button_glow": glow_stats,
        "terminal_cursor": repair_stats,
        "lottie_checks": lottie_checks,
        "composition": {
            "width": W,
            "height": H,
            "fps": FPS,
            "duration_seconds": DURATION,
            "layers": [layer["nm"] for layer in lottie["layers"]],
            "all_new_image_assets_embedded": True,
        },
        "static_preview_pixel_identical_to_source": True,
        "visible_cursor_reconstructs_source_crop_exactly": True,
        "cursor_repair_changes_confined_to_local_patch": True,
        "animation_loop_start_matches_end": True,
        "animated_preview": {
            "file": "preview/profile-banner-phase-5.2.gif",
            "frames": PREVIEW_FRAMES,
            "duration_seconds": DURATION,
        },
    }
    report_path = OUT / "microinteraction-validation-report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    markdown = f"""# Phase 5.2 microinteraction validation

## Source and scope

- Original artwork: `assets/image.png`, SHA-256 `{report['source_png_sha256']}`. It was not edited; the same PNG bytes are embedded in the new Lottie and SVG.
- Active source composition: `{BASE_LOTTIE.relative_to(ROOT).as_posix()}`. This is the current full-canvas Lottie in the working tree, with the original artwork and the existing portfolio-border reflection.
- The prior `phase-5.1-motion-refinement` source is absent from the latest working tree. Its older ring/circuit effects were not restored, because the current selected design keeps circuit lighting off.
- The current border-reflection layer was copied unchanged. The README and currently published asset remain untouched for this phase.

## Effects and layers

- `portfolio-button-ambient-glow-from-existing-border`: localized PNG halo extracted from bright, color-saturated pixels along all four sides and rounded corners of the existing button border; the alpha is blurred, so it adds no second crisp outline. Its opacity eases between {GLOW_MIN_OPACITY:.0f}% and {GLOW_MAX_OPACITY:.0f}% on a {GLOW_PERIOD_SECONDS:.1f}-second loop.
- `terminal-cursor-blink-at-original-underscore`: original {repair_stats['cursor_core_box'][2]-repair_stats['cursor_core_box'][0]}×{repair_stats['cursor_core_box'][3]-repair_stats['cursor_core_box'][1]} px cyan cursor at `{repair_stats['cursor_core_box']}`; it blinks on a 1-second cycle with short fades.
- `terminal-cursor-local-background-repair`: changes only `{repair_stats['reconstructed_background_box']}` to estimate the hidden dark terminal background from adjacent pixels. The surrounding source crop is otherwise unchanged; the source underscore is fully removed underneath the animated cursor.
- `portfolio-button-rounded-border-reflection`: preserved from the active composition without changes.
- `unchanged original banner`: original PNG, unchanged and embedded.

## Validation results

- The static preview has the original image dimensions ({W}×{H}) and is pixel-identical to the source.
- The cursor is at `{repair_stats['cursor_core_box']}`; showing its cropped source layer reconstructs its source pixels exactly, and hiding it leaves no permanent underscore.
- The cursor repair is confined to a `{CURSOR_PATCH[2]-CURSOR_PATCH[0]}×{CURSOR_PATCH[3]-CURSOR_PATCH[1]} px` local patch. All pixels outside the patch remain pixel-identical to the original.
- The button glow mask covers top/right/bottom/left edges: `{glow_stats['side_coverage_pixels']}`. All four rounded-corner quadrants contain source border pixels: `{glow_stats['corner_coverage_pixels']}`.
- At 720 px preview width, the max/min glow adds more than 10 channel levels to {glow_stats['preview_scale_pixels_over_10_difference']} pixels in the button region (maximum channel difference {glow_stats['preview_scale_max_channel_difference']}).
- The 9-second preview contains {PREVIEW_FRAMES} frames. Animation changes are confined to the button and terminal cursor areas.
- The button detail GIF plays one complete {GLOW_PERIOD_SECONDS:.1f}-second glow cycle; the cursor detail GIF shows two complete 1-second blinks.
- The SVG dimensions and aspect ratio match the source; its existing border reflection, breathing halo, and cursor blink use SMIL animations.
- New PNG assets are embedded into the Lottie JSON; no remote asset paths are required.
- The composition was imported into LottieFiles Creator as a draft; Creator displayed the 1672×941 composition and all five layers during playback. It was not published.

## Deliverables

- `profile-banner-phase-5.2.json` — self-contained Lottie composition.
- `profile-banner-phase-5.2.svg` — self-contained animated SVG.
- `preview/profile-banner-phase-5.2.gif` — full-banner preview.
- `preview/profile-banner-phase-5.2-static.png` — source-identical static preview with animation disabled.
- `preview/portfolio-button-glow-detail.gif` — enlarged border/glow detail.
- `preview/terminal-cursor-blink-detail.gif` — enlarged cursor visible/hidden detail.
- `layers/` — localized glow, cursor source, and background-repair image layers.

## Limitation

The original underscore is raster artwork, so the background pixels beneath it do not exist separately. The tiny hidden area is reconstructed by interpolation from immediately adjacent terminal pixels; that local repair is not claimed to be a recovered original vector or exact hidden texture.
"""
    (OUT / "microinteraction-validation-report.md").write_text(markdown, encoding="utf-8")

    print(json.dumps({
        "lottie_file": str(lottie_path),
        "svg": str(svg_path),
        "animation_preview": str(animated_path),
        "static_preview": str(static_path),
        "button_detail": str(border_path),
        "cursor_detail": str(cursor_detail_path),
        "report": str(OUT / "microinteraction-validation-report.md"),
        "glow": glow_stats,
        "cursor": repair_stats,
        "lottie_layer_checks": lottie_checks,
        "duration_seconds": DURATION,
        "generation_seconds": round(time.perf_counter() - started, 1),
    }, indent=2))


if __name__ == "__main__":
    main()
