"""Build a standalone banner variant with motion only on the portfolio button border."""

from __future__ import annotations

import base64
import hashlib
import json
import math
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
PREVIEW_DIR = OUT / "preview"
SOURCE = ROOT / "assets" / "image.png"
W, H = 1672, 941
FPS = 30
DURATION = 9.0
END_FRAME = int(FPS * DURATION)
PREVIEW_SIZE = (720, 405)
PREVIEW_FRAMES = 180
REFLECTION_LENGTH = 190.0
REFLECTION_PHASE = 0.17
REFLECTION_PERIOD = DURATION
RADIUS = 13.0
HANDLE = RADIUS * 0.552284749831
GRADIENT_STOPS = [
    (0.0, (132, 238, 255)),
    (0.52, (116, 177, 255)),
    (1.0, (212, 157, 255)),
]
BUTTON_SVG_PATH = (
    "M1025 451 H1582 A13 13 0 0 1 1595 464 V592 "
    "A13 13 0 0 1 1582 605 H1025 A13 13 0 0 1 1012 592 "
    "V464 A13 13 0 0 1 1025 451 Z"
)
BUTTON_LOTTIE_VERTICES = [
    (1025.0, 451.0), (1582.0, 451.0), (1595.0, 464.0),
    (1595.0, 592.0), (1582.0, 605.0), (1025.0, 605.0),
    (1012.0, 592.0), (1012.0, 464.0),
]


def lengths(points: list[tuple[float, float]]) -> tuple[list[float], float]:
    segments = [math.dist(a, b) for a, b in zip(points, points[1:])]
    return segments, sum(segments)


def sampled_button_path(steps_per_corner: int = 32) -> list[tuple[float, float]]:
    points = [(1025.0, 451.0), (1582.0, 451.0)]
    arcs = [
        ((1582.0, 464.0), -math.pi / 2, 0.0),
        ((1582.0, 592.0), 0.0, math.pi / 2),
        ((1025.0, 592.0), math.pi / 2, math.pi),
        ((1025.0, 464.0), math.pi, 3 * math.pi / 2),
    ]
    for index, (center, start, end) in enumerate(arcs):
        for step in range(1, steps_per_corner + 1):
            angle = start + (end - start) * step / steps_per_corner
            points.append((center[0] + RADIUS * math.cos(angle),
                           center[1] + RADIUS * math.sin(angle)))
        if index == 0:
            points.append((1595.0, 592.0))
        elif index == 1:
            points.append((1025.0, 605.0))
        elif index == 2:
            points.append((1012.0, 464.0))
    return points


BUTTON_PATH_POINTS = sampled_button_path()
BUTTON_SEGMENT_LENGTHS, BUTTON_PERIMETER = lengths(BUTTON_PATH_POINTS)
TRIM_START = 1.0 - REFLECTION_LENGTH / BUTTON_PERIMETER


def point_at(distance: float) -> tuple[float, float]:
    position = distance % BUTTON_PERIMETER
    for (a, b), segment_length in zip(zip(BUTTON_PATH_POINTS, BUTTON_PATH_POINTS[1:]),
                                      BUTTON_SEGMENT_LENGTHS):
        if position <= segment_length:
            q = position / segment_length if segment_length else 0.0
            return (a[0] + (b[0] - a[0]) * q,
                    a[1] + (b[1] - a[1]) * q)
        position -= segment_length
    return BUTTON_PATH_POINTS[0]


def progress_at(seconds: float) -> float:
    return (seconds / REFLECTION_PERIOD + REFLECTION_PHASE) % 1.0


def gradient_color(x: float) -> tuple[int, int, int]:
    position = min(1.0, max(0.0, (x - 1012.0) / (1595.0 - 1012.0)))
    for (left_position, left_color), (right_position, right_color) in zip(
            GRADIENT_STOPS, GRADIENT_STOPS[1:]):
        if position <= right_position:
            amount = ((position - left_position) / (right_position - left_position)
                      if right_position != left_position else 0.0)
            return tuple(round(a + (b - a) * amount)
                         for a, b in zip(left_color, right_color))
    return GRADIENT_STOPS[-1][1]


def lottie_gradient_stroke(name: str, opacity: float, width: float) -> dict:
    gradient = []
    for position, (red, green, blue) in GRADIENT_STOPS:
        gradient.extend([position, red / 255, green / 255, blue / 255])
    gradient.extend([0, 1, 1, 1])
    return {
        "ty": "gs", "nm": name,
        "o": {"a": 0, "k": opacity}, "w": {"a": 0, "k": width},
        "g": {"p": len(GRADIENT_STOPS), "k": {"a": 0, "k": gradient}},
        "t": 1, "s": {"a": 0, "k": [1012, 451]},
        "e": {"a": 0, "k": [1595, 451]},
        "lc": 2, "lj": 2, "ml": 2, "bm": 0,
    }


def keyframes(ticks: list[int], values: list[float]) -> list[dict]:
    output = []
    for index in range(len(ticks) - 1):
        output.append({
            "t": ticks[index], "s": [values[index]], "e": [values[index + 1]],
            "i": {"x": [0.333], "y": [0.333]},
            "o": {"x": [0.667], "y": [0.667]}, "h": 0,
        })
    output.append({
        "t": ticks[-1], "s": [values[-1]], "e": [values[-1]],
        "i": {"x": [0.333], "y": [0.333]},
        "o": {"x": [0.667], "y": [0.667]}, "h": 0,
    })
    return output


def make_button_layer(ticks: list[int]) -> dict:
    vertices = [[x, y] for x, y in BUTTON_LOTTIE_VERTICES]
    incoming = [
        [-HANDLE, 0], [0, 0], [0, -HANDLE], [0, 0],
        [HANDLE, 0], [0, 0], [0, HANDLE], [0, 0],
    ]
    outgoing = [
        [0, 0], [HANDLE, 0], [0, 0], [0, HANDLE],
        [0, 0], [-HANDLE, 0], [0, 0], [0, -HANDLE],
    ]
    offsets = [360.0 * progress_at(frame / FPS) for frame in ticks]
    trim = {
        "ty": "tm",
        "s": {"a": 0, "k": 100.0 * TRIM_START},
        "e": {"a": 0, "k": 100},
        "o": {"a": 1, "k": keyframes(ticks, offsets)},
        "m": 1,
        "nm": "moving highlight along button border",
    }
    shapes = [{
        "ty": "gr",
        "nm": "Explore My Portfolio rounded border light",
        "it": [
            {"ind": 0, "ty": "sh", "nm": "rounded button border",
             "ks": {"a": 0, "k": {"i": incoming, "o": outgoing,
                                     "v": vertices, "c": True}}},
            lottie_gradient_stroke("visible color-matched border reflection", 96, 3.6),
            lottie_gradient_stroke("fine edge sheen", 66, 1.25),
            trim,
            {"ty": "tr", "nm": "Transform",
             "p": {"a": 0, "k": [0, 0]}, "a": {"a": 0, "k": [0, 0]},
             "s": {"a": 0, "k": [100, 100]}, "r": {"a": 0, "k": 0},
             "o": {"a": 0, "k": 100}, "sk": {"a": 0, "k": 0},
             "sa": {"a": 0, "k": 0}},
        ],
    }]
    return {
        "ddd": 0, "ind": 1, "ty": 4,
        "nm": "portfolio-button-rounded-border-reflection", "sr": 1,
        "ks": {
            "o": {"a": 0, "k": 100}, "r": {"a": 0, "k": 0},
            "p": {"a": 0, "k": [0, 0, 0]}, "a": {"a": 0, "k": [0, 0, 0]},
            "s": {"a": 0, "k": [100, 100, 100]},
        },
        "ao": 0, "shapes": shapes, "ip": 0, "op": END_FRAME, "st": 0, "bm": 0,
    }


def embedded_png_asset(source_bytes: bytes) -> dict:
    encoded = base64.b64encode(source_bytes).decode("ascii")
    return {"id": "original-banner", "w": W, "h": H, "u": "",
            "p": "data:image/png;base64," + encoded, "e": 1}


def base_layer() -> dict:
    return {
        "ddd": 0, "ind": 2, "ty": 2, "nm": "unchanged original banner",
        "refId": "original-banner", "sr": 1,
        "ks": {
            "o": {"a": 0, "k": 100}, "r": {"a": 0, "k": 0},
            "p": {"a": 0, "k": [0, 0, 0]}, "a": {"a": 0, "k": [0, 0, 0]},
            "s": {"a": 0, "k": [100, 100, 100]},
        },
        "ao": 0, "ip": 0, "op": END_FRAME, "st": 0, "bm": 0,
    }


def build_svg(source_bytes: bytes, destination: Path) -> None:
    encoded = base64.b64encode(source_bytes).decode("ascii")
    start_distance = (TRIM_START + REFLECTION_PHASE) * BUTTON_PERIMETER
    dasharray = f"{REFLECTION_LENGTH:.4f} {BUTTON_PERIMETER - REFLECTION_LENGTH:.4f}"
    offsets = f"{-start_distance:.4f};{-start_distance - BUTTON_PERIMETER:.4f}"
    initial_offset = -start_distance
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" role="img" aria-labelledby="title description">',
        '<title id="title">Profile banner — only the portfolio button border is animated</title>',
        '<desc id="description">The original banner stays unchanged. A bright cyan-to-violet reflection travels only along the rounded Explore My Portfolio border, matching its existing colors; the circuit artwork remains static.</desc>',
        '<defs><linearGradient id="button-reflection" gradientUnits="userSpaceOnUse" '
        'x1="1012" y1="451" x2="1595" y2="451">'
        '<stop offset="0%" stop-color="#84eeff"/><stop offset="52%" stop-color="#74b1ff"/>'
        '<stop offset="100%" stop-color="#d49dff"/></linearGradient></defs>',
        f'<image id="original-banner" x="0" y="0" width="{W}" height="{H}" '
        f'href="data:image/png;base64,{encoded}"/>',
        '<g id="portfolio-button-border-only" pointer-events="none">',
    ]
    for width, opacity in ((3.6, 0.96), (1.25, 0.66)):
        lines.extend([
            f'<path d="{BUTTON_SVG_PATH}" pathLength="{BUTTON_PERIMETER:.4f}" fill="none" '
            f'stroke="url(#button-reflection)" stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round" '
            f'stroke-dasharray="{dasharray}" stroke-dashoffset="{initial_offset:.4f}" opacity="{opacity}">',
            f'<animate attributeName="stroke-dashoffset" values="{offsets}" dur="{DURATION:.3f}s" '
            'repeatCount="indefinite" calcMode="linear"/>',
            '</path>',
        ])
    lines.extend(['</g>', '</svg>'])
    destination.write_text("\n".join(lines), encoding="utf-8")


def reflection_overlay(seconds: float) -> Image.Image:
    scale = 2
    canvas_size = (PREVIEW_SIZE[0] * scale, PREVIEW_SIZE[1] * scale)
    sx, sy = canvas_size[0] / W, canvas_size[1] / H
    start = ((TRIM_START + progress_at(seconds)) % 1.0) * BUTTON_PERIMETER
    samples = max(2, math.ceil(REFLECTION_LENGTH / 2.0))
    path = []
    for index in range(samples + 1):
        x, y = point_at(start + REFLECTION_LENGTH * index / samples)
        path.append((round(x * sx), round(y * sy)))

    def gradient_stroke(width: int, alpha: int) -> Image.Image:
        layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        for first, second in zip(path, path[1:]):
            source_x = ((first[0] + second[0]) / 2) / sx
            color = gradient_color(source_x)
            draw.line([first, second], fill=(*color, alpha), width=width)
        for endpoint in (path[0], path[-1]):
            source_x = endpoint[0] / sx
            radius = width / 2
            color = (*gradient_color(source_x), alpha)
            draw.ellipse((endpoint[0] - radius, endpoint[1] - radius,
                          endpoint[0] + radius, endpoint[1] + radius), fill=color)
        return layer

    reflection = gradient_stroke(4, 242)
    reflection.alpha_composite(gradient_stroke(2, 160))
    return reflection.resize(PREVIEW_SIZE, Image.Resampling.LANCZOS)


def render_preview_frame(base: Image.Image, seconds: float) -> Image.Image:
    frame = base.convert("RGBA")
    frame.alpha_composite(reflection_overlay(seconds))
    return frame.convert("RGB")


def save_gif(frames: list[Image.Image], base: Image.Image, destination: Path) -> None:
    # Build one palette from the static artwork, then replace only pixels
    # touched by the light. This prevents palette dithering from animating
    # background pixels elsewhere in the banner.
    palette = base.convert("P", palette=Image.Palette.ADAPTIVE, colors=256)
    background = base.quantize(palette=palette, dither=Image.Dither.FLOYDSTEINBERG)
    indexed = []
    for frame in frames:
        rgb = frame.convert("RGB")
        changed = ImageChops.difference(rgb, base).convert("L")
        mask = changed.point(lambda value: 255 if value else 0)
        quantized = rgb.quantize(palette=palette, dither=Image.Dither.NONE)
        indexed_frame = background.copy()
        indexed_frame.paste(quantized, mask=mask)
        indexed.append(indexed_frame)
    indexed[0].save(destination, save_all=True, append_images=indexed[1:],
                     duration=round(DURATION * 1000 / len(frames)), loop=0,
                     disposal=1, optimize=True)


def write_text_if_changed(destination: Path, content: str) -> None:
    if not destination.exists() or destination.read_text(encoding="utf-8") != content:
        destination.write_text(content, encoding="utf-8")


def main() -> None:
    started = time.perf_counter()
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    source_bytes = SOURCE.read_bytes()
    source = Image.open(SOURCE).convert("RGB")
    if source.size != (W, H):
        raise ValueError(f"Expected original artwork at {W}x{H}, got {source.size}")
    route_samples = [point_at(BUTTON_PERIMETER * index / 32) for index in range(32)]
    route_x = [point[0] for point in route_samples]
    route_y = [point[1] for point in route_samples]
    if min(route_x) > 1013 or max(route_x) < 1594 or min(route_y) > 452 or max(route_y) < 604:
        raise AssertionError("The highlight path does not traverse all four button edges")

    ticks = list(range(0, END_FRAME, 3)) + [END_FRAME]
    values = [360.0 * progress_at(frame / FPS) for frame in ticks]
    asset = embedded_png_asset(source_bytes)
    doc = {
        "v": "5.13.0", "fr": FPS, "ip": 0, "op": END_FRAME,
        "w": W, "h": H, "nm": "Profile banner — button border light only", "ddd": 0,
        "assets": [asset], "layers": [make_button_layer(ticks), base_layer()], "markers": [],
    }

    json_path = OUT / "profile-banner-button-only.json"
    svg_path = OUT / "profile-banner-button-only.svg"
    json_path.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    build_svg(source_bytes, svg_path)

    # Confirm that the original PNG is embedded byte-for-byte and not re-encoded.
    embedded = base64.b64decode(doc["assets"][0]["p"].split(",", 1)[1])
    if embedded != source_bytes:
        raise AssertionError("The original image was altered while embedding it")

    base_preview = source.resize(PREVIEW_SIZE, Image.Resampling.LANCZOS)
    frames = [render_preview_frame(base_preview, DURATION * index / PREVIEW_FRAMES)
              for index in range(PREVIEW_FRAMES)]
    static_path = PREVIEW_DIR / "profile-banner-button-only-static.png"
    gif_path = PREVIEW_DIR / "profile-banner-button-only.gif"
    frames[45].save(static_path, optimize=True)
    save_gif(frames, base_preview, gif_path)

    # Confirm the optimized output preserves its timing and confines movement
    # to the button when decoded as an animated GIF.
    with Image.open(gif_path) as animation:
        if animation.n_frames != PREVIEW_FRAMES:
            raise AssertionError("The GIF encoder dropped or merged animation frames")
        gif_duration_ms = 0
        animation.seek(0)
        first_gif_frame = animation.convert("RGB")
        protected_region = (round(990 * PREVIEW_SIZE[0] / W),
                            round(430 * PREVIEW_SIZE[1] / H),
                            round(1610 * PREVIEW_SIZE[0] / W),
                            round(625 * PREVIEW_SIZE[1] / H))
        moving_frame_diff = None
        for frame_index in range(animation.n_frames):
            animation.seek(frame_index)
            gif_duration_ms += animation.info.get("duration", 0)
            current_frame = animation.convert("RGB")
            difference = ImageChops.difference(current_frame, first_gif_frame)
            outside_button = difference.copy()
            ImageDraw.Draw(outside_button).rectangle(protected_region, fill=(0, 0, 0))
            if outside_button.getbbox() is not None:
                raise AssertionError("The decoded GIF changes pixels outside the button")
            if frame_index == PREVIEW_FRAMES // 2:
                moving_frame_diff = difference.crop(protected_region).getbbox()
        if gif_duration_ms != round(DURATION * 1000):
            raise AssertionError("The GIF duration is not one complete 9-second loop")
        if moving_frame_diff is None:
            raise AssertionError("The GIF does not show a moving button-border highlight")

    svg_root = ET.parse(svg_path).getroot()
    if len(svg_root.findall(".//{http://www.w3.org/2000/svg}path")) != 2:
        raise AssertionError("The SVG should contain only the two slim button-border strokes")
    if len(doc["layers"]) != 2 or len(doc["assets"]) != 1:
        raise AssertionError("The Lottie variant should contain only the original image and button shape")

    start_frame = render_preview_frame(base_preview, 0)
    end_frame = render_preview_frame(base_preview, DURATION)
    loop_difference = ImageChops.difference(start_frame, end_frame)
    if loop_difference.getbbox() is not None:
        raise AssertionError("The 9-second button-light loop does not close seamlessly")

    # The generated preview may differ from the source only near the existing button border.
    comparison = ImageChops.difference(frames[45], base_preview)
    outside_button = comparison.copy()
    sx, sy = PREVIEW_SIZE[0] / W, PREVIEW_SIZE[1] / H
    protected_region = (round(990 * sx), round(430 * sy), round(1610 * sx), round(625 * sy))
    ImageDraw.Draw(outside_button).rectangle(protected_region, fill=(0, 0, 0))
    if outside_button.getbbox() is not None:
        raise AssertionError("Animation affected pixels outside the button region")

    html = PREVIEW_DIR / "preview.html"
    write_text_if_changed(html,
        '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Portfolio button border-only animation</title>'
        '<style>body{margin:0;padding:20px;background:#080a10;color:#eaf2ff;font:14px system-ui,sans-serif}'
        'main{max-width:1000px;margin:auto}img{display:block;width:100%;height:auto}p{color:#9cb4d8}</style>'
        '<main><img src="../profile-banner-button-only.svg" alt="Original banner with a moving light only on the rounded portfolio button border">'
        '<p>Only the Explore My Portfolio border moves. The circuit artwork remains static.</p></main>',
    )
    lottie_html = PREVIEW_DIR / "lottie-preview.html"
    write_text_if_changed(lottie_html,
        '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Portfolio button-border-only Lottie preview</title>'
        '<style>body{margin:0;padding:20px;background:#080a10;color:#eaf2ff;font:14px system-ui,sans-serif}'
        'main{max-width:1000px;margin:auto}#banner{width:100%;aspect-ratio:1672/941;background:#05070c}'
        '#status{margin-top:10px;color:#9cb4d8}</style>'
        '<main><div id="banner" role="img" aria-label="Original banner with only the portfolio button border animated"></div>'
        '<p id="status">Loading the two-layer Lottie composition…</p></main>'
        '<script src="/node_modules/lottie-web/build/player/lottie.min.js"></script><script>'
        'const status=document.getElementById("status");const animation=bodymovin.loadAnimation({container:document.getElementById("banner"),'
        'renderer:"svg",loop:true,autoplay:true,path:"../profile-banner-button-only.json",'
        'rendererSettings:{preserveAspectRatio:"xMidYMid meet"}});'
        'animation.addEventListener("DOMLoaded",()=>{status.textContent="Lottie-Web loaded; only the portfolio button border moves.";});'
        'animation.addEventListener("data_failed",()=>{status.textContent="Lottie JSON failed to load.";});</script>',
    )

    source_hash = hashlib.sha256(source_bytes).hexdigest()
    report = f"""# Portfolio button-border-only variant

## Composition

- `profile-banner-button-only.svg`: self-contained animated SVG with the original PNG embedded byte-for-byte.
- `profile-banner-button-only.json`: self-contained Lottie composition with one unchanged image layer and one native rounded-border shape layer.
- `preview/profile-banner-button-only.gif`: 9-second optimized animated preview; a visible cyan-to-violet highlight travels only along the Explore My Portfolio border.
- `preview/profile-banner-button-only-static.png`: representative frame at 2.25 seconds.
- `preview/preview.html` and `preview/lottie-preview.html`: local SVG and Lottie-Web previews.

## Motion scope

The only animated effect is a visible cyan-to-violet reflection moving around the existing 13 px rounded button border. Its color shifts from cyan on the left to blue and violet on the right to blend with the existing edge. A 190 px highlight and fine bright core travel directly along the contour, with round caps and the border's cubic corner curves carrying it through each turn instead of rotating it as a rectangle. The README embeds the GIF because its frame-based animation remains visible in GitHub's Markdown renderer. The original circuit lines, ring, typography, icons, terminal, and remaining artwork stay as they are in the static source image; no circuit-light effects are added.

## Checks

- Original source: `{SOURCE.relative_to(ROOT).as_posix()}`; SHA-256 `{source_hash}`.
- The PNG embedded in the SVG and Lottie file matches the source bytes exactly.
- The SVG parses as XML and contains only two button-border strokes.
- The GIF retains {PREVIEW_FRAMES} frames, lasts 9 seconds, and keeps all frame-to-frame changes inside the button region after decoding.
- Lottie contains {len(doc['layers'])} layers: one native vector border effect and the original image.
- Pixels outside the button area match the static source in the generated preview.
- Opening and closing frames are identical at preview size; no loop seam is visible.
- Preview: {len(frames)} frames at {round(DURATION * 1000 / len(frames))} ms each; SVG {svg_path.stat().st_size:,} bytes; Lottie {json_path.stat().st_size:,} bytes; GIF {gif_path.stat().st_size:,} bytes.
- Generation time: {time.perf_counter() - started:.1f} seconds.
"""
    (OUT / "design-notes.md").write_text(report, encoding="utf-8")
    print(json.dumps({
        "svg": str(svg_path), "lottie": str(json_path), "gif": str(gif_path),
        "static": str(static_path), "layers": len(doc["layers"]),
        "base_sha256": source_hash, "base_bytes_unchanged": embedded == source_bytes,
        "svg_button_strokes": len(svg_root.findall(".//{http://www.w3.org/2000/svg}path")),
        "pixels_unchanged_outside_button": outside_button.getbbox() is None,
        "loop_difference_pixels": 0,
    }, indent=2))


if __name__ == "__main__":
    main()
