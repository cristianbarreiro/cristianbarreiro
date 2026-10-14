"""Build the isolated Phase 3 SVG, Lottie, and inspectable raster previews."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "assets" / "phase-3-animation"
SOURCE = ROOT / "assets" / "phase-2-layered"
SIZE = (1672, 941)
FPS = 30
DURATION = 9.0
TOTAL_FRAMES = round(FPS * DURATION)

ROI = {
    "circuit": (0, 195, 118, 234),
    "button": (1110, 449, 1580, 453),
    "ambient": (10, 10, 190, 118),
}


def pulse(t: float, phase: float = 0.0) -> float:
    return 0.5 + 0.5 * math.sin(2 * math.pi * (t / DURATION) + phase)


def read_base_data_uri() -> str:
    tree = ET.parse(SOURCE / "profile-banner-layered.svg")
    image = tree.find(".//{http://www.w3.org/2000/svg}image[@id='phase-1-foundation-image']")
    if image is None:
        raise ValueError("Phase 2 base image ID was not found")
    uri = image.get("href") or image.get("{http://www.w3.org/1999/xlink}href")
    if not uri or not uri.startswith("data:image/png;base64,"):
        raise ValueError("Phase 2 base image is not embedded as expected")
    return uri


def source_mask(name: str) -> Image.Image:
    path = SOURCE / "layers" / f"{name}-overlay.png"
    image = Image.open(path).convert("RGBA")
    if image.size != SIZE:
        raise ValueError(f"Unexpected overlay dimensions: {path} {image.size}")
    return image.getchannel("A")


def tinted_glow(mask: Image.Image, roi: tuple[int, int, int, int], blur: float,
                start: tuple[int, int, int], end: tuple[int, int, int],
                strength: float, core: float) -> Image.Image:
    """Tint only a blurred copy of existing mask alpha, clipped to its source ROI."""
    soft = mask.filter(ImageFilter.GaussianBlur(blur))
    hard = mask
    glow = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    pix = glow.load()
    sp, hp = soft.load(), hard.load()
    x0, y0, x1, y1 = roi
    width = max(1, x1 - x0 - 1)
    for y in range(y0, y1):
        for x in range(x0, x1):
            a = min(170, round(sp[x, y] * strength + hp[x, y] * core))
            if not a:
                continue
            f = (x - x0) / width
            color = tuple(round(start[i] + (end[i] - start[i]) * f) for i in range(3))
            pix[x, y] = (*color, a)
    return glow


def save_png(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", optimize=True)


def composite_at(base: Image.Image, glows: dict[str, Image.Image], t: float) -> Image.Image:
    frame = base.copy().convert("RGBA")
    opacities = {
        "circuit": 0.52 + 0.28 * pulse(t),
        "button": 0.42 + 0.34 * pulse(t, -math.pi / 2),
        "ambient": 0.48 + 0.27 * pulse(t, math.pi / 2),
    }
    for key in ("ambient", "circuit", "button"):
        glow = glows[key]
        alpha = glow.getchannel("A").point(lambda v: round(v * opacities[key]))
        layer = glow.copy()
        layer.putalpha(alpha)
        frame.alpha_composite(layer)
    return frame


def animated_keyframes(kind: str) -> list[dict]:
    phase = {"circuit": 0.0, "button": -math.pi / 2, "ambient": math.pi / 2}[kind]
    low, high = {"circuit": (0.52, 0.80), "button": (0.42, 0.76), "ambient": (0.48, 0.75)}[kind]
    frames = []
    stops = (0, 45, 90, 135, 180, 225, 270)
    for frame, next_frame in zip(stops, stops[1:]):
        p = 0.5 + 0.5 * math.sin(2 * math.pi * frame / TOTAL_FRAMES + phase)
        next_p = 0.5 + 0.5 * math.sin(2 * math.pi * next_frame / TOTAL_FRAMES + phase)
        frames.append({"t": frame, "s": [round(100 * (low + (high - low) * p), 3)], "e": [round(100 * (low + (high - low) * next_p), 3)], "i": {"x": [0.333], "y": [0.333]}, "o": {"x": [0.667], "y": [0.667]}, "h": 0})
    p = 0.5 + 0.5 * math.sin(2 * math.pi + phase)
    last = round(100 * (low + (high - low) * p), 3)
    frames.append({"t": 270, "s": [last], "e": [last], "i": {"x": [0.333], "y": [0.333]}, "o": {"x": [0.667], "y": [0.667]}, "h": 0})
    return frames


def svg_document(base_uri: str, effects: dict[str, Image.Image]) -> str:
    data = {key: "data:image/png;base64," + base64.b64encode(_png_bytes(img)).decode("ascii") for key, img in effects.items()}
    anim = {
        "circuit": ("0.66;0.8;0.66;0.52;0.66", "9s", "0s"),
        "button": ("0.42;0.59;0.76;0.59;0.42", "9s", "0s"),
        "ambient": ("0.75;0.615;0.48;0.615;0.75", "9s", "0s"),
    }
    effect_markup = []
    ids = {"circuit": "circuit-light-overlay", "button": "button-highlight-overlay", "ambient": "ambient-light-overlay"}
    for key in ("circuit", "button", "ambient"):
        vals, dur, begin = anim[key]
        label = ids[key]
        effect_markup.append(f'''  <g id="{label}" aria-hidden="true" data-derived-from="{label.replace('-overlay', '-overlay-raster')}">
    <image id="{label}-glow" x="0" y="0" width="1672" height="941" href="{data[key]}" />
    <animate attributeName="opacity" values="{vals}" dur="{dur}" begin="{begin}" repeatCount="indefinite" calcMode="spline" keyTimes="0;0.25;0.5;0.75;1" keySplines="0.42 0 0.58 1;0.42 0 0.58 1;0.42 0 0.58 1;0.42 0 0.58 1" />
  </g>''')
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="1672" height="941" viewBox="0 0 1672 941" role="img" aria-labelledby="title description" preserveAspectRatio="xMidYMid meet">
  <title id="title">Cristian Barreiro — Phase 3 animated banner proof of concept</title>
  <desc id="description">The original banner remains a static embedded image. Smooth localized luminous overlays are derived only from the three existing Phase 2 raster selections.</desc>
  <metadata>9-second seamless SVG animation. Original composition remains static. The overlays are colored, blurred derivatives of existing raster masks; no banner geometry has been reconstructed. No terminal cursor overlay is available.</metadata>
  <g id="base-artwork"><image id="phase-1-foundation-image" x="0" y="0" width="1672" height="941" href="{base_uri}" /></g>
{chr(10).join(effect_markup)}
</svg>
'''


def _png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def build_lottie(base: Image.Image, effects: dict[str, Image.Image]) -> None:
    folder = OUT / "lottie" / "images"
    folder.mkdir(parents=True, exist_ok=True)
    save_png(base.convert("RGBA"), folder / "base-artwork.png")
    assets = [{"id": "image_base", "w": SIZE[0], "h": SIZE[1], "u": "lottie/images/", "p": "base-artwork.png", "e": 0}]
    layers = []
    layer_specs = [
        ("button", "button-highlight-overlay", 3),
        ("circuit", "circuit-light-overlay", 2),
        ("ambient", "ambient-light-overlay", 1),
    ]
    for key, layer_name, index in layer_specs:
        filename = f"{key}-glow.png"
        save_png(effects[key], folder / filename)
        ref = f"image_{key}"
        assets.append({"id": ref, "w": SIZE[0], "h": SIZE[1], "u": "lottie/images/", "p": filename, "e": 0})
        layers.append({
            "ddd": 0, "ind": index, "ty": 2, "nm": layer_name, "refId": ref,
            "sr": 1, "ks": {"o": {"a": 1, "k": animated_keyframes(key)}, "r": {"a": 0, "k": 0},
                              "p": {"a": 0, "k": [0, 0, 0]}, "a": {"a": 0, "k": [0, 0, 0]},
                              "s": {"a": 0, "k": [100, 100, 100]}},
            "ao": 0, "ip": 0, "op": TOTAL_FRAMES, "st": 0, "bm": 0,
        })
    layers.append({"ddd": 0, "ind": 4, "ty": 2, "nm": "base-artwork", "refId": "image_base", "sr": 1,
                   "ks": {"o": {"a": 0, "k": 100}, "r": {"a": 0, "k": 0}, "p": {"a": 0, "k": [0, 0, 0]},
                          "a": {"a": 0, "k": [0, 0, 0]}, "s": {"a": 0, "k": [100, 100, 100]}},
                   "ao": 0, "ip": 0, "op": TOTAL_FRAMES, "st": 0, "bm": 0})
    document = {"v": "5.12.2", "fr": FPS, "ip": 0, "op": TOTAL_FRAMES, "w": SIZE[0], "h": SIZE[1],
                "nm": "Profile banner — Phase 3 effect proof of concept", "ddd": 0, "assets": assets, "layers": layers,
                "markers": []}
    (OUT / "profile-banner-animated.json").write_text(json.dumps(document, indent=2), encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    base_path = ROOT / "assets" / "image.png"
    base = Image.open(base_path).convert("RGBA")
    if base.size != SIZE:
        raise ValueError(f"Unexpected source dimensions {base.size}")
    base_data_uri = read_base_data_uri()
    masks = {
        "circuit": source_mask("circuit-light"),
        "button": source_mask("button-highlight"),
        "ambient": source_mask("ambient-light"),
    }
    glows = {
        "circuit": tinted_glow(masks["circuit"], ROI["circuit"], 1.5, (45, 108, 255), (56, 231, 255), 0.66, 0.30),
        "button": tinted_glow(masks["button"], ROI["button"], 0.85, (85, 165, 255), (140, 240, 255), 0.46, 0.45),
        "ambient": tinted_glow(masks["ambient"], ROI["ambient"], 4.2, (75, 89, 230), (105, 123, 255), 0.37, 0.08),
    }
    svg = svg_document(base_data_uri, glows)
    (OUT / "profile-banner-animated.svg").write_text(svg, encoding="utf-8")

    representative_time = 1.5
    representative = composite_at(base, glows, representative_time)
    save_png(representative, OUT / "profile-banner-animation-preview.png")

    frame_count = 18
    gif_frames = [composite_at(base, glows, DURATION * i / frame_count).convert("RGB") for i in range(frame_count)]
    gif_frames = [frame.quantize(colors=256, method=Image.Quantize.MEDIANCUT) for frame in gif_frames]
    gif_frames[0].save(OUT / "profile-banner-animation-preview.gif", save_all=True, append_images=gif_frames[1:],
                       duration=500, loop=0, optimize=True, disposal=1)
    build_lottie(base, glows)

    source_hashes = {}
    for path in [base_path, ROOT / "assets" / "profile-banner-foundation.svg", SOURCE / "profile-banner-layered.svg",
                 *sorted((SOURCE / "layers").glob("*.png")), ROOT / "assets" / "profile-banner-animated.svg"]:
        source_hashes[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    (OUT / "source-hashes.json").write_text(json.dumps(source_hashes, indent=2), encoding="utf-8")

    preview_ref = Image.open(SOURCE / "profile-banner-layered-preview.png").convert("RGBA")
    if ImageChops.difference(base, preview_ref).getbbox() is not None:
        raise AssertionError("Phase 2 preview no longer matches the original artwork")
    if representative.size != SIZE or ImageChops.difference(base.convert("RGB"), representative.convert("RGB")).getbbox() is None:
        raise AssertionError("Representative frame is not a visible full-size effect frame")
    check = Image.open(OUT / "profile-banner-animation-preview.gif")
    if getattr(check, "n_frames", 1) < 2:
        raise AssertionError("Animation preview did not contain changing frames")
    print(f"Created Phase 3 outputs at {OUT}; GIF frames: {check.n_frames}; dimensions: {check.size}")


if __name__ == "__main__":
    main()
