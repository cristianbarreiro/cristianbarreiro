"""Create Phase 4 raster selections and their SVG/Lottie effect compositions."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "assets" / "phase-4-layer-expansion"
PHASE2 = ROOT / "assets" / "phase-2-layered"
PHASE3 = ROOT / "assets" / "phase-3-animation"
SOURCE = ROOT / "assets" / "image.png"
W, H = 1672, 941
FPS, FRAMES = 30, 270
DURATION = FRAMES / FPS
SVG_NS = "http://www.w3.org/2000/svg"


def pixels_on_polyline(points: list[tuple[float, float]], width: float = 2.6,
                       node: tuple[float, float, float] | None = None):
    """Yield source-pixel locations near a visible trace; never draw the guide path."""
    segments = list(zip(points, points[1:]))
    min_x = max(0, math.floor(min(p[0] for p in points) - width - (node[2] if node else 0)))
    max_x = min(W, math.ceil(max(p[0] for p in points) + width + (node[2] if node else 0) + 1))
    min_y = max(0, math.floor(min(p[1] for p in points) - width - (node[2] if node else 0)))
    max_y = min(H, math.ceil(max(p[1] for p in points) + width + (node[2] if node else 0) + 1))
    yield min_x, min_y, max_x, max_y, segments, node, width


def line_distance(px: float, py: float, a: tuple[float, float], b: tuple[float, float]) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length_sq = dx * dx + dy * dy
    if not length_sq:
        return math.hypot(px - a[0], py - a[1])
    t = min(1.0, max(0.0, ((px - a[0]) * dx + (py - a[1]) * dy) / length_sq))
    return math.hypot(px - (a[0] + t * dx), py - (a[1] + t * dy))


def extract_trace(source: Image.Image, points: list[tuple[float, float]],
                  node: tuple[float, float, float] | None = None) -> Image.Image:
    rgba = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    out = rgba.load()
    src = source.load()
    x0, y0, x1, y1, segments, node, width = next(pixels_on_polyline(points, node=node))
    for y in range(y0, y1):
        for x in range(x0, x1):
            d = min(line_distance(x + 0.5, y + 0.5, a, b) for a, b in segments)
            in_node = node and math.hypot(x + 0.5 - node[0], y + 0.5 - node[1]) <= node[2]
            if d > width and not in_node:
                continue
            color = src[x, y]
            chroma = max(color) - min(color)
            peak = max(color)
            if chroma < 30 or peak < 28:
                continue
            # Chroma carries a soft alpha through the anti-aliased source edges.
            alpha = min(255, max(0, round((chroma - 18) * 1.48)))
            if in_node and math.hypot(x + 0.5 - node[0], y + 0.5 - node[1]) < node[2] - 2:
                alpha = max(alpha, min(255, round((chroma - 12) * 1.6)))
            if alpha:
                out[x, y] = (*color, alpha)
    return rgba


def extract_button(source: Image.Image) -> dict[str, Image.Image]:
    """Select the chromatic original contour inside a rounded-rectangle corridor."""
    pix = source.load()
    masks = {name: Image.new("RGBA", (W, H), (0, 0, 0, 0)) for name in
             ("button-top-border", "button-bottom-border", "button-left-border", "button-right-border", "button-corner-regions")}
    out = {name: image.load() for name, image in masks.items()}
    left, right, top, bottom, radius = 1012, 1595, 451, 605, 13
    cx, cy = (left + right) / 2, (top + bottom) / 2
    half_w, half_h = (right - left - 2 * radius) / 2, (bottom - top - 2 * radius) / 2
    for y in range(444, 613):
        for x in range(1003, 1605):
            qx = abs((x + 0.5) - cx) - half_w
            qy = abs((y + 0.5) - cy) - half_h
            distance = min(max(qx, qy), 0) + math.hypot(max(qx, 0), max(qy, 0)) - radius
            if abs(distance) > 2.7:
                continue
            color = pix[x, y]
            chroma, peak = max(color) - min(color), max(color)
            if chroma < 25 or peak < 50:
                continue
            alpha = min(255, max(0, round((chroma - 18) * 1.42)))
            if not alpha:
                continue
            if ((x < 1038 and y < 479) or (x > 1572 and y < 479) or
                (x < 1038 and y > 578) or (x > 1572 and y > 578)):
                key = "button-corner-regions"
            elif 1038 <= x <= 1572 and y < 479:
                key = "button-top-border"
            elif 1038 <= x <= 1572 and y > 578:
                key = "button-bottom-border"
            elif x < 1038 and 479 <= y <= 578:
                key = "button-left-border"
            elif x > 1572 and 479 <= y <= 578:
                key = "button-right-border"
            else:
                continue
            out[key][x, y] = (*color, alpha)
    return masks


def brighten_within_matte(matte: Image.Image, ratio: float) -> Image.Image:
    """Brighten only selected source pixels; retain their exact spatial footprint."""
    src = matte.load()
    effect = Image.new("RGBA", matte.size, (0, 0, 0, 0))
    dst = effect.load()
    bbox = matte.getchannel("A").getbbox()
    if bbox:
        x0, y0, x1, y1 = bbox
        for y in range(y0, y1):
            for x in range(x0, x1):
                r, g, b, a = src[x, y]
                if not a:
                    continue
                color = tuple(min(255, round(c + (255 - c) * ratio)) for c in (r, g, b))
                dst[x, y] = (*color, round(a * 0.78))
    return effect


def halo_from_matte(matte: Image.Image, color: tuple[int, int, int], radius: float) -> Image.Image:
    """Create a soft, localized halo from an existing source-pixel mask."""
    alpha = matte.getchannel("A").filter(ImageFilter.GaussianBlur(radius))
    halo = Image.new("RGBA", matte.size, (*color, 0))
    halo.putalpha(alpha.point(lambda a: round(a * 0.68)))
    return halo


def png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def data_uri(image: Image.Image) -> str:
    return "data:image/png;base64," + base64.b64encode(png_bytes(image)).decode("ascii")


def phase3_data() -> tuple[str, dict[str, Image.Image]]:
    raw_svg = (PHASE3 / "profile-banner-animated.svg").read_text(encoding="utf-8")
    root = ET.fromstring(raw_svg)
    base_el = root.find(f".//{{{SVG_NS}}}image[@id='phase-1-foundation-image']")
    if base_el is None:
        raise ValueError("Phase 3 embedded base layer was not found")
    base_uri = base_el.get("href")
    if not base_uri or not base_uri.startswith("data:image/png;base64,"):
        raise ValueError("Phase 3 base layer is not embedded")
    old_effects = {}
    for name in ("circuit-light-overlay", "button-highlight-overlay", "ambient-light-overlay"):
        group = root.find(f".//{{{SVG_NS}}}g[@id='{name}']")
        image = group.find(f".//{{{SVG_NS}}}image") if group is not None else None
        href = image.get("href") if image is not None else None
        if not href or not href.startswith("data:image/png;base64,"):
            raise ValueError(f"Phase 3 effect {name} is missing or external")
        old_effects[name] = Image.open(io.BytesIO(base64.b64decode(href.split(",", 1)[1]))).convert("RGBA")
    return base_uri, old_effects


def make_svg(base_uri: str, effect_layers: dict[str, Image.Image]) -> str:
    original = (PHASE3 / "profile-banner-animated.svg").read_text(encoding="utf-8")
    original = original.replace("Phase 3 animated banner proof of concept", "Phase 4 circuit and button layer expansion")
    original = original.replace("three existing Phase 2 raster selections", "validated Phase 2 selections and Phase 4 extracted source-pixel masks")
    original = original.replace("The overlays are colored, blurred derivatives of existing raster masks; no banner geometry has been reconstructed. No terminal cursor overlay is available.",
                                "The existing composition remains static beneath independently controlled Phase 2 glow effects and Phase 4 raster selections. No banner geometry has been reconstructed. The terminal cursor remains part of the base.")
    insert_at = original.rfind("</svg>")
    if insert_at < 0:
        raise ValueError("Phase 3 SVG root close was not found")
    names = list(effect_layers)
    values = {
        "circuit-upper-trace-overlay": (0.52, 0.96, 0.24, 0.00),
        "circuit-mid-upper-trace-overlay": (0.48, 0.90, 0.22, 0.70),
        "button-top-border": (0.38, 0.78, 0.14, 0.00),
        "button-bottom-border": (0.38, 0.78, 0.14, math.pi),
        "button-left-border": (0.34, 0.72, 0.12, math.pi / 2),
        "button-right-border": (0.34, 0.72, 0.12, -math.pi / 2),
        "button-corner-regions": (0.32, 0.68, 0.10, math.pi / 2),
        "circuit-upper-trace-overlay-halo": (0.18, 0.68, 0.20, 0.00),
        "circuit-mid-upper-trace-overlay-halo": (0.16, 0.62, 0.18, 0.70),
        "button-top-border-halo": (0.16, 0.54, 0.10, 0.00),
        "button-bottom-border-halo": (0.16, 0.54, 0.10, math.pi),
        "button-left-border-halo": (0.14, 0.50, 0.08, math.pi / 2),
        "button-right-border-halo": (0.14, 0.50, 0.08, -math.pi / 2),
        "button-corner-regions-halo": (0.12, 0.48, 0.08, math.pi / 2),
    }
    append = []
    for name in names:
        low, high, _, phase = values[name]
        stops = [round(low + (high - low) * (0.5 + 0.5 * math.sin(2 * math.pi * t / DURATION + phase)), 4)
                 for t in (0, 2.25, 4.5, 6.75, 9)]
        splines = " ".join(["0.42 0 0.58 1"] * 4)
        append.append(f'''  <g id="{name}" aria-hidden="true" data-source-pixels="true">
    <image id="{name}-effect-image" x="0" y="0" width="{W}" height="{H}" href="{data_uri(effect_layers[name])}" />
    <animate attributeName="opacity" values="{';'.join(map(str, stops))}" dur="9s" begin="0s" repeatCount="indefinite" calcMode="spline" keyTimes="0;0.25;0.5;0.75;1" keySplines="{splines}" />
  </g>''')
    return original[:insert_at] + "\n" + "\n".join(append) + "\n" + original[insert_at:]


def opacity_keys(low: float, high: float, phase: float) -> list[dict]:
    stops = [0, 45, 90, 135, 180, 225, 270]
    def value(frame: int) -> float:
        p = 0.5 + 0.5 * math.sin(2 * math.pi * frame / FRAMES + phase)
        return round(100 * (low + (high - low) * p), 4)
    result = []
    for start, end in zip(stops, stops[1:]):
        result.append({"t": start, "s": [value(start)], "e": [value(end)], "i": {"x": [0.333], "y": [0.333]}, "o": {"x": [0.667], "y": [0.667]}, "h": 0})
    result.append({"t": 270, "s": [value(270)], "e": [value(270)], "i": {"x": [0.333], "y": [0.333]}, "o": {"x": [0.667], "y": [0.667]}, "h": 0})
    return result


def make_lottie(effect_layers: dict[str, Image.Image], source_layers: dict[str, Image.Image]) -> None:
    out_images = OUT / "lottie" / "images"
    out_images.mkdir(parents=True, exist_ok=True)
    old_doc = json.loads((PHASE3 / "profile-banner-animated.json").read_text(encoding="utf-8"))
    old_assets = {a["id"]: a for a in old_doc["assets"]}
    for asset in old_doc["assets"]:
        src = PHASE3 / asset.get("u", "") / asset["p"]
        dest = out_images / asset["p"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
    doc = dict(old_doc)
    doc["nm"] = "Profile banner — Phase 4 circuit and button regions"
    specs = [
        ("circuit-upper-trace-overlay", 0.52, 0.96, 0.0),
        ("circuit-mid-upper-trace-overlay", 0.48, 0.90, 0.70),
        ("button-top-border", 0.38, 0.78, 0.0),
        ("button-bottom-border", 0.38, 0.78, math.pi),
        ("button-left-border", 0.34, 0.72, math.pi / 2),
        ("button-right-border", 0.34, 0.72, -math.pi / 2),
        ("button-corner-regions", 0.32, 0.68, math.pi / 2),
        ("circuit-upper-trace-overlay-halo", 0.18, 0.68, 0.20),
        ("circuit-mid-upper-trace-overlay-halo", 0.16, 0.62, 0.70),
        ("button-top-border-halo", 0.16, 0.54, 0.10),
        ("button-bottom-border-halo", 0.16, 0.54, math.pi),
        ("button-left-border-halo", 0.14, 0.50, math.pi / 2),
        ("button-right-border-halo", 0.14, 0.50, -math.pi / 2),
        ("button-corner-regions-halo", 0.12, 0.48, math.pi / 2),
    ]
    new_assets, new_layers = [], []
    next_ind = max(layer["ind"] for layer in doc["layers"]) + 1
    for offset, (name, low, high, phase) in enumerate(specs):
        png_name = name + "-effect.png"
        (out_images / png_name).write_bytes(png_bytes(effect_layers[name]))
        ref_id = "phase4_" + name
        new_assets.append({"id": ref_id, "w": W, "h": H, "u": "lottie/images/", "p": png_name, "e": 0})
        new_layers.append({
            "ddd": 0, "ind": next_ind + offset, "ty": 2, "nm": name, "refId": ref_id, "sr": 1,
            "ks": {"o": {"a": 1, "k": opacity_keys(low, high, phase)}, "r": {"a": 0, "k": 0},
                   "p": {"a": 0, "k": [0, 0, 0]}, "a": {"a": 0, "k": [0, 0, 0]},
                   "s": {"a": 0, "k": [100, 100, 100]}},
            "ao": 0, "ip": 0, "op": FRAMES, "st": 0, "bm": 0,
        })
    doc["assets"] = doc["assets"] + new_assets
    # Image-layer arrays are ordered top-to-bottom. Place Phase 4 overlays above Phase 3.
    base_layers = [layer for layer in doc["layers"] if layer.get("nm") == "base-artwork"]
    other_layers = [layer for layer in doc["layers"] if layer.get("nm") != "base-artwork"]
    doc["layers"] = new_layers + other_layers + base_layers
    (OUT / "profile-banner-phase-4.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")


def pulse(low: float, high: float, phase: float, t: float) -> float:
    return low + (high - low) * (0.5 + 0.5 * math.sin(2 * math.pi * t / DURATION + phase))


def composite(base: Image.Image, effects: dict[str, Image.Image], t: float) -> Image.Image:
    result = base.convert("RGBA").copy()
    # Retain the Phase 3 layer motion and its relative stacking order.
    old_ops = {
        "ambient-light-overlay": pulse(0.48, 0.75, math.pi / 2, t),
        "circuit-light-overlay": pulse(0.52, 0.80, 0.0, t),
        "button-highlight-overlay": pulse(0.42, 0.76, -math.pi / 2, t),
    }
    for name in ("ambient-light-overlay", "circuit-light-overlay", "button-highlight-overlay"):
        layer = effects[name].copy()
        layer.putalpha(layer.getchannel("A").point(lambda a: round(a * old_ops[name])))
        result.alpha_composite(layer)
    phases = {
        "circuit-upper-trace-overlay": (0.52, 0.96, 0.0),
        "circuit-mid-upper-trace-overlay": (0.48, 0.90, 0.70),
        "button-top-border": (0.38, 0.78, 0.0),
        "button-bottom-border": (0.38, 0.78, math.pi),
        "button-left-border": (0.34, 0.72, math.pi / 2),
        "button-right-border": (0.34, 0.72, -math.pi / 2),
        "button-corner-regions": (0.32, 0.68, math.pi / 2),
        "circuit-upper-trace-overlay-halo": (0.18, 0.68, 0.20),
        "circuit-mid-upper-trace-overlay-halo": (0.16, 0.62, 0.70),
        "button-top-border-halo": (0.16, 0.54, 0.10),
        "button-bottom-border-halo": (0.16, 0.54, math.pi),
        "button-left-border-halo": (0.14, 0.50, math.pi / 2),
        "button-right-border-halo": (0.14, 0.50, -math.pi / 2),
        "button-corner-regions-halo": (0.12, 0.48, math.pi / 2),
    }
    for name, (low, high, phase) in phases.items():
        layer = effects[name].copy()
        layer.putalpha(layer.getchannel("A").point(lambda a, op=pulse(low, high, phase, t): round(a * op)))
        result.alpha_composite(layer)
    return result


def save_gif(frames: list[Image.Image], path: Path, duration_ms: int = 500) -> None:
    """Write opaque full-frame GIFs with a shared palette and clean frame disposal."""
    if not frames:
        raise ValueError("Cannot write an empty GIF")
    thumb_w = max(1, frames[0].width // 6)
    thumb_h = max(1, frames[0].height // 6)
    columns = min(6, len(frames))
    rows = math.ceil(len(frames) / columns)
    sheet = Image.new("RGB", (columns * thumb_w, rows * thumb_h))
    for index, frame in enumerate(frames):
        thumb = frame.convert("RGB").resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)
        sheet.paste(thumb, ((index % columns) * thumb_w, (index // columns) * thumb_h))
    palette = sheet.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
    indexed = [frame.convert("RGB").quantize(palette=palette, dither=Image.Dither.NONE)
               for frame in frames]
    indexed[0].save(path, save_all=True, append_images=indexed[1:], duration=duration_ms,
                    loop=0, optimize=True, disposal=2)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    source = Image.open(SOURCE).convert("RGB")
    if source.size != (W, H):
        raise ValueError(f"Unexpected source dimensions: {source.size}")
    (OUT / "layers").mkdir(exist_ok=True)

    circuit_mattes = {
        "circuit-upper-trace": extract_trace(source, [(1263, 70), (1338, 70), (1373, 37), (1671, 37)], (1263, 70, 7)),
        "circuit-mid-upper-trace": extract_trace(source, [(1115, 143), (1172, 143), (1218, 99), (1338, 99)], (1338, 99, 2.2)),
    }
    button_mattes = extract_button(source)
    source_mattes = {**circuit_mattes, **button_mattes}
    for name, matte in source_mattes.items():
        matte.save(OUT / "layers" / f"{name}.png", optimize=True)

    effect_layers = {name + "-overlay" if name in circuit_mattes else name: brighten_within_matte(matte, 0.82 if name in circuit_mattes else 0.70)
                     for name, matte in source_mattes.items()}
    # Normalize circuit source layer names to their explicit Phase 4 IDs.
    effect_layers["circuit-upper-trace-overlay"] = effect_layers.pop("circuit-upper-trace-overlay")
    effect_layers["circuit-mid-upper-trace-overlay"] = effect_layers.pop("circuit-mid-upper-trace-overlay")
    halo_colors = {
        "circuit-upper-trace-overlay": (76, 210, 255),
        "circuit-mid-upper-trace-overlay": (91, 191, 255),
        "button-top-border": (104, 194, 255),
        "button-bottom-border": (112, 173, 255),
        "button-left-border": (120, 159, 255),
        "button-right-border": (95, 198, 255),
        "button-corner-regions": (112, 175, 255),
    }
    for source_name, color in halo_colors.items():
        matte_name = source_name.removesuffix("-overlay")
        effect_layers[source_name + "-halo"] = halo_from_matte(source_mattes[matte_name], color, 2.2 if "circuit" in source_name else 1.8)
    for name, effect in effect_layers.items():
        effect.save(OUT / "layers" / f"{name}-effect.png", optimize=True)

    base_uri, phase3_effects = phase3_data()
    svg = make_svg(base_uri, effect_layers)
    (OUT / "profile-banner-phase-4.svg").write_text(svg, encoding="utf-8")
    static_groups = []
    for name in ("ambient-light-overlay", "circuit-light-overlay", "button-highlight-overlay"):
        static_groups.append(f'''<g id="{name}" opacity="0"><image x="0" y="0" width="{W}" height="{H}" href="{data_uri(phase3_effects[name])}"/></g>''')
    for name, effect in effect_layers.items():
        static_groups.append(f'''<g id="{name}" opacity="0"><image x="0" y="0" width="{W}" height="{H}" href="{data_uri(effect)}"/></g>''')
    static_svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="{SVG_NS}" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="title description" preserveAspectRatio="xMidYMid meet">
  <title id="title">Phase 4 banner — static fidelity state</title>
  <desc id="description">The original artwork and all Phase 3 and Phase 4 effect layers, with every effect layer disabled.</desc>
  <g id="base-artwork"><image id="phase-1-foundation-image" x="0" y="0" width="{W}" height="{H}" href="{base_uri}"/></g>
  {' '.join(static_groups)}
</svg>
'''
    (OUT / "profile-banner-phase-4-static.svg").write_text(static_svg, encoding="utf-8")

    # Static proof: the base-only state is the original raster, with an exact zero difference.
    source_rgba = source.convert("RGBA")
    source_rgba.save(OUT / "profile-banner-phase-4-static-preview.png", optimize=True)
    phase1 = Image.open(ROOT / "assets" / "profile-banner-foundation-preview.png").convert("RGB")
    static_difference = ImageChops.difference(source.convert("RGB"), phase1)
    static_difference.save(OUT / "phase-4-static-difference.png", optimize=True)
    if static_difference.getbbox() is not None:
        raise AssertionError("Phase 4 base-only preview differs from Phase 1 foundation")

    all_effects = dict(phase3_effects)
    all_effects.update(effect_layers)
    frames = [composite(source_rgba, all_effects, t).convert("RGB") for t in (4.5,)]
    frames[0].save(OUT / "profile-banner-phase-4-animation-frame.png", optimize=True)
    gif_frames = [composite(source_rgba, all_effects, DURATION * i / 18).convert("RGB") for i in range(18)]
    save_gif(gif_frames, OUT / "profile-banner-phase-4-animation-preview.gif")
    readme_frames = [frame.resize((1100, 619), Image.Resampling.LANCZOS) for frame in gif_frames]
    save_gif(readme_frames, OUT / "profile-banner-phase-4-readme.gif")
    make_lottie(effect_layers, source_mattes)

    protected = [ROOT / "assets" / "image.png", ROOT / "assets" / "profile-banner-foundation.svg",
                 ROOT / "assets" / "profile-banner-animated.svg"]
    protected.extend(p for p in (ROOT / "assets" / "phase-2-layered").rglob("*") if p.is_file())
    protected.extend(p for p in PHASE3.rglob("*") if p.is_file())
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    (OUT / "protected-source-hashes.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")

    metrics = {}
    for name, matte in source_mattes.items():
        alpha = matte.getchannel("A")
        bbox = alpha.getbbox()
        metrics[name] = {"pixels": sum(alpha.histogram()[1:]), "bbox": bbox}
    (OUT / "extraction-metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    if not gif_frames or len(gif_frames) != 18:
        raise AssertionError("Phase 4 animated preview frame count is invalid")
    print(f"Phase 4 composition created: {OUT}")
    print(f"Static pixel comparison exact; difference bounding box: {static_difference.getbbox()}")
    print("Extracted masks:", json.dumps(metrics, separators=(",", ":")))


if __name__ == "__main__":
    main()
