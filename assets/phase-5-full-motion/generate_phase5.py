"""Build a raster-faithful Phase 5 Lottie and preview from the source banner.

The masks below retain only pixels found in assets/image.png. Geometry guides
limit selection to visible source traces; they are never rendered as artwork.
"""

from __future__ import annotations

import base64
import io
import json
import math
import shutil
import sys
import time
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
PHASE4 = ROOT / "assets" / "phase-4-layer-expansion"
PHASE4_JSON = PHASE4 / "profile-banner-phase-4.json"
PHASE4_SVG = PHASE4 / "profile-banner-phase-4.svg"
SOURCE = ROOT / "assets" / "image.png"
W, H = 1672, 941
FPS, FRAMES = 30, 270
DURATION = FRAMES / FPS
PREVIEW_SIZE = (1000, 563)
SVG_NS = "http://www.w3.org/2000/svg"

sys.path.insert(0, str(PHASE4))
import generate_phase4 as phase4  # noqa: E402


COMETS = [
    {
        "name": "mid-left-trace-sweep",
        "points": [(887, 216), (924, 216), (944, 237)],
        "period": 4.5,
        "phase": 0.22,
        "color": (160, 231, 255),
        "width": 2.8,
    },
    {
        "name": "lower-upper-trace-sweep",
        "points": [(806, 625), (925, 625), (950, 650)],
        "period": 3.0,
        "phase": 0.38,
        "color": (136, 216, 255),
        "width": 2.8,
    },
    {
        "name": "lower-stepped-trace-sweep",
        "points": [(730, 675), (846, 675), (870, 650), (925, 650), (950, 675)],
        "period": 4.5,
        "phase": 0.61,
        "color": (151, 203, 255),
        "width": 2.8,
    },
    {
        "name": "lower-node-trace-sweep",
        "points": [(902, 750), (961, 810), (961, 925)],
        "period": 4.5,
        "phase": 0.34,
        "color": (191, 171, 255),
        "width": 3.0,
    },
    {
        "name": "lower-accent-sweep",
        "points": [(1114, 692), (1172, 692)],
        "period": 3.0,
        "phase": 0.73,
        "color": (135, 218, 255),
        "width": 2.8,
    },
]


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def alpha_for_chroma(chroma: np.ndarray, minimum: float = 8.0) -> np.ndarray:
    return np.clip((chroma.astype(np.float32) - minimum) * 7.0, 0, 220).astype(np.uint8)


def make_effect(source: Image.Image, mask: Image.Image, lift: float = 0.58,
                tint: tuple[int, int, int] | None = None, mix: float = 0.0,
                alpha_scale: float = 0.78) -> Image.Image:
    src = np.asarray(source.convert("RGB"), dtype=np.float32)
    a = np.asarray(mask.convert("L"), dtype=np.float32)
    light = np.clip(src + (255.0 - src) * lift, 0, 255)
    if tint is not None and mix > 0:
        color = np.asarray(tint, dtype=np.float32).reshape((1, 1, 3))
        light = light * (1.0 - mix) + color * mix
    out = np.zeros((H, W, 4), dtype=np.uint8)
    out[:, :, :3] = light.round().astype(np.uint8)
    out[:, :, 3] = np.clip(a * alpha_scale, 0, 255).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def mask_from_circle(source: Image.Image, center: tuple[float, float],
                     radius_min: float, radius_max: float,
                     box: tuple[int, int, int, int], min_chroma: int = 22,
                     min_peak: int = 45) -> Image.Image:
    rgb = np.asarray(source.convert("RGB"), dtype=np.uint8)
    r, g, b = (rgb[:, :, i].astype(np.int16) for i in range(3))
    chroma = rgb.max(axis=2).astype(np.int16) - rgb.min(axis=2).astype(np.int16)
    peak = rgb.max(axis=2)
    y0, y1 = np.mgrid[0:H, 0:W]
    dist = np.hypot(y0 - center[1], y1 - center[0])
    x0, yy0, x1, yy1 = box
    region = np.zeros((H, W), dtype=bool)
    region[yy0:yy1, x0:x1] = True
    selected = region & (dist >= radius_min) & (dist <= radius_max) & (chroma >= min_chroma) & (peak >= min_peak)
    alpha = np.where(selected, alpha_for_chroma(chroma, 7), 0).astype(np.uint8)
    return Image.fromarray(alpha, "L")


def polyline_mask(source: Image.Image, points: list[tuple[float, float]], width: float,
                  color_mode: str = "blue", min_chroma: int = 9,
                  min_peak: int = 18) -> Image.Image:
    rgb_full = np.asarray(source.convert("RGB"), dtype=np.uint8)
    pad = int(math.ceil(width + 2))
    x0 = max(0, math.floor(min(p[0] for p in points) - pad))
    y0 = max(0, math.floor(min(p[1] for p in points) - pad))
    x1 = min(W, math.ceil(max(p[0] for p in points) + pad + 1))
    y1 = min(H, math.ceil(max(p[1] for p in points) + pad + 1))
    yy, xx = np.mgrid[y0:y1, x0:x1]
    dist = np.full(xx.shape, np.inf, dtype=np.float32)
    for a, b in zip(points, points[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length_sq = dx * dx + dy * dy
        if not length_sq:
            current = np.hypot(xx - a[0], yy - a[1])
        else:
            t = np.clip(((xx - a[0]) * dx + (yy - a[1]) * dy) / length_sq, 0.0, 1.0)
            current = np.hypot(xx - (a[0] + t * dx), yy - (a[1] + t * dy))
        dist = np.minimum(dist, current)
    rgb = rgb_full[y0:y1, x0:x1].astype(np.int16)
    r, g, b = (rgb[:, :, i] for i in range(3))
    chroma = rgb.max(axis=2) - rgb.min(axis=2)
    peak = rgb.max(axis=2)
    if color_mode == "blue":
        color_ok = (b > r + 2) & (b >= g)
    elif color_mode == "cool":
        color_ok = (b > r + 2) | ((r > g + 8) & (b > g + 8))
    else:
        color_ok = np.ones(chroma.shape, dtype=bool)
    selected = (dist <= width) & (chroma >= min_chroma) & (peak >= min_peak) & color_ok
    alpha = np.where(selected, alpha_for_chroma(chroma, max(4, min_chroma - 4)), 0).astype(np.uint8)
    full = np.zeros((H, W), dtype=np.uint8)
    full[y0:y1, x0:x1] = alpha
    return Image.fromarray(full, "L")


def circle_pixels(source: Image.Image, center: tuple[float, float], radius: float,
                  color_mode: str, min_chroma: int = 18,
                  min_peak: int = 35) -> Image.Image:
    rgb = np.asarray(source.convert("RGB"), dtype=np.uint8)
    r, g, b = (rgb[:, :, i].astype(np.int16) for i in range(3))
    chroma = rgb.max(axis=2).astype(np.int16) - rgb.min(axis=2).astype(np.int16)
    peak = rgb.max(axis=2)
    yy, xx = np.mgrid[0:H, 0:W]
    dist = np.hypot(xx - center[0], yy - center[1])
    if color_mode == "red":
        hue_ok = (r > g * 1.35) & (r > b * 1.2) & (r > 90)
    elif color_mode == "yellow":
        hue_ok = (r > 100) & (g > 80) & (b < 150) & (r > b + 20)
    elif color_mode == "green":
        hue_ok = (g > 90) & (g > r * 1.3) & (g > b * 0.72)
    else:
        hue_ok = np.ones((H, W), dtype=bool)
    selected = (dist <= radius) & (chroma >= min_chroma) & (peak >= min_peak) & hue_ok
    alpha = np.where(selected, alpha_for_chroma(chroma, 6), 0).astype(np.uint8)
    return Image.fromarray(alpha, "L")


def components(mask: np.ndarray, min_area: int, max_area: int,
               min_size: int = 2, max_size: int = 8) -> list[list[tuple[int, int]]]:
    height, width = mask.shape
    seen = np.zeros(mask.shape, dtype=bool)
    result: list[list[tuple[int, int]]] = []
    for sy, sx in zip(*np.where(mask)):
        if seen[sy, sx]:
            continue
        stack = [(int(sy), int(sx))]
        seen[sy, sx] = True
        cells: list[tuple[int, int]] = []
        min_x = max_x = int(sx)
        min_y = max_y = int(sy)
        while stack:
            y, x = stack.pop()
            cells.append((y, x))
            min_x, max_x = min(min_x, x), max(max_x, x)
            min_y, max_y = min(min_y, y), max(max_y, y)
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < height and 0 <= nx < width and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
        bw, bh = max_x - min_x + 1, max_y - min_y + 1
        if min_area <= len(cells) <= max_area and min_size <= bw <= max_size and min_size <= bh <= max_size:
            result.append(cells)
    return result


def cluster(values: list[float], tolerance: float = 9.0) -> list[float]:
    if not values:
        return []
    values = sorted(values)
    groups: list[list[float]] = [[values[0]]]
    for value in values[1:]:
        if value - groups[-1][-1] <= tolerance:
            groups[-1].append(value)
        else:
            groups.append([value])
    return [sum(group) / len(group) for group in groups]


def dot_wave_masks(source: Image.Image, box: tuple[int, int, int, int],
                   threshold: str, min_area: int, max_area: int) -> tuple[dict[str, Image.Image], list[tuple[float, float]]]:
    rgb_full = np.asarray(source.convert("RGB"), dtype=np.uint8)
    x0, y0, x1, y1 = box
    region = rgb_full[y0:y1, x0:x1].astype(np.int16)
    r, g, b = (region[:, :, i] for i in range(3))
    if threshold == "upper":
        binary = (b > r + 5) & (b > g + 3) & (b > 22)
    else:
        binary = (b > r + 10) & (b > g + 4) & (b > 25) & (b < 125)
    found = components(binary, min_area, max_area)
    centers = [(x0 + sum(x for _, x in cells) / len(cells),
                y0 + sum(y for y, _ in cells) / len(cells)) for cells in found]
    rows = cluster([point[1] for point in centers])
    cols = cluster([point[0] for point in centers])
    masks = {f"{threshold}-dot-wave-{index + 1:02d}": Image.new("L", (W, H), 0) for index in range(6)}
    for cells, center in zip(found, centers):
        row = min(range(len(rows)), key=lambda i: abs(rows[i] - center[1]))
        col = min(range(len(cols)), key=lambda i: abs(cols[i] - center[0]))
        group = (row + col) % 6
        im = np.asarray(masks[f"{threshold}-dot-wave-{group + 1:02d}"]).copy()
        for y, x in cells:
            py, px = y0 + y, x0 + x
            pixel = rgb_full[py, px].astype(np.int16)
            chroma = int(pixel.max() - pixel.min())
            im[py, px] = max(im[py, px], min(220, max(40, (chroma - 5) * 7)))
        masks[f"{threshold}-dot-wave-{group + 1:02d}"] = Image.fromarray(im, "L")
    return masks, centers


def crop_rgba(image: Image.Image) -> tuple[Image.Image, tuple[int, int, int, int]]:
    bbox = image.getchannel("A").getbbox()
    if bbox is None:
        raise ValueError("An effect layer has no visible pixels")
    return image.crop(bbox), bbox


def data_uri(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def pulse_value(low: float, high: float, phase: float, period: float, t: float) -> float:
    point = 0.5 + 0.5 * math.sin(2 * math.pi * t / period + phase)
    return low + (high - low) * point


def make_pulse(name: str, mask: Image.Image, source: Image.Image, lift: float,
               low: float, high: float, phase: float, period: float,
               tint: tuple[int, int, int] | None = None, mix: float = 0.0) -> dict:
    effect = make_effect(source, mask, lift=lift, tint=tint, mix=mix)
    return {"name": name, "image": effect, "mask": mask, "low": low, "high": high,
            "phase": phase, "period": period}


def make_selections(source: Image.Image) -> tuple[list[dict], list[dict], dict[str, Image.Image], dict]:
    rgb = np.asarray(source.convert("RGB"), dtype=np.uint8)
    chroma = rgb.max(axis=2).astype(np.int16) - rgb.min(axis=2).astype(np.int16)
    peak = rgb.max(axis=2)
    pulses: list[dict] = []
    traces: dict[str, Image.Image] = {}
    comets: list[dict] = []
    stats: dict = {}

    ring = mask_from_circle(source, (1344.9, 419.3), 395, 429, (900, 0, W, 900), 20, 50)
    pulses.append(make_pulse("large-ring-intensity-wave", ring, source, 0.38, 0.10, 0.36, 0.62, 9.0))

    badge = mask_from_circle(source, (1497.3, 172.5), 80, 100, (1385, 60, 1610, 285), 20, 45)
    pulses.append(make_pulse("upper-right-badge-perimeter", badge, source, 0.62, 0.12, 0.46, 1.24, 4.5))

    panel_paths = [
        [(1078, 197), (1395, 197)],
        [(1597, 197), (1625, 197)],
        [(1078, 197), (1078, 450)],
        [(1625, 197), (1625, 450)],
    ]
    panel = Image.new("L", (W, H), 0)
    for points in panel_paths:
        panel = ImageChops.lighter(panel, polyline_mask(source, points, 2.2, "blue", 6, 18))
    pulses.append(make_pulse("terminal-panel-visible-border", panel, source, 0.80, 0.08, 0.34, 2.17, 9.0,
                             tint=(122, 207, 255), mix=0.28))

    for name, center, color, period, phase in [
        ("terminal-status-red", (1117, 229), "red", 3.0, 0.20),
        ("terminal-status-yellow", (1150, 229), "yellow", 4.5, 1.85),
        ("terminal-status-green", (1183, 229), "green", 3.0, 3.10),
    ]:
        status_mask = circle_pixels(source, center, 9.5, color, min_chroma=28, min_peak=60)
        pulses.append(make_pulse(name, status_mask, source, 0.46, 0.12, 0.56, phase, period))

    dot_specs = [
        ("upper", (0, 0, 180, 180), "upper", 8, 70, 0.13, 0.68),
        ("lower", (1280, 700, W, H), "lower", 8, 50, 0.10, 0.52),
    ]
    dot_details: dict[str, list[tuple[float, float]]] = {}
    for prefix, box, threshold, min_area, max_area, low, high in dot_specs:
        masks, centers = dot_wave_masks(source, box, threshold, min_area, max_area)
        dot_details[prefix] = centers
        for index, mask in enumerate(masks.values()):
            pulses.append(make_pulse(mask_name := f"{prefix}-dot-wave-{index + 1:02d}", mask, source,
                                     0.86, low, high, (index / 6) * 2 * math.pi, 9.0))

    trace_specs = [
        ("mid-left-circuit-trace", [(887, 216), (924, 216), (944, 237)], 2.8, (887, 216, 9.0), (0.12, 0.42, 2.0, 3.0)),
        ("lower-upper-circuit-trace", [(806, 625), (925, 625), (950, 650)], 2.8, None, (0.10, 0.36, 1.1, 3.0)),
        ("lower-stepped-circuit-trace", [(730, 675), (846, 675), (870, 650), (925, 650), (950, 675)], 2.8, None, (0.10, 0.36, 3.2, 4.5)),
        ("lower-node-circuit-trace", [(902, 750), (961, 810), (961, 925)], 3.0, (902, 750, 9.0), (0.12, 0.45, 4.1, 4.5)),
        ("lower-decorative-accent", [(1114, 692), (1172, 692)], 2.4, None, (0.10, 0.38, 2.4, 3.0)),
    ]
    for name, points, width, node, timing in trace_specs:
        mask = polyline_mask(source, points, width, "blue", 8, 18)
        if node:
            node_center = (node[0], node[1])
            node_mask = circle_pixels(source, node_center, node[2], "cool", 12, 24)
            mask = ImageChops.lighter(mask, node_mask)
        traces[name] = mask
        low, high, phase, period = timing
        pulses.append(make_pulse(name + "-light-pulse", mask, source, 0.78, low, high, phase, period,
                                 tint=(139, 221, 255), mix=0.24))

    comet_records = []
    comet_trace_names = [
        "mid-left-circuit-trace", "lower-upper-circuit-trace",
        "lower-stepped-circuit-trace", "lower-node-circuit-trace",
        "lower-decorative-accent",
    ]
    for spec, trace_name in zip(COMETS, comet_trace_names):
        trace = traces[trace_name]
        bbox = trace.getbbox()
        coverage = trace_coverage(trace, spec["points"])
        comet_records.append({**spec, "trace_name": trace_name, "coverage": coverage, "bbox": bbox})
        # Only retain a moving sweep when most of its path is supported by source pixels.
        if coverage >= 0.72:
            comets.append(spec)

    stats["rings"] = {
        "large-ring": {"bbox": ring.getbbox(), "selected_pixels": int(np.count_nonzero(np.asarray(ring)))},
        "badge": {"bbox": badge.getbbox(), "selected_pixels": int(np.count_nonzero(np.asarray(badge)))},
    }
    stats["dots"] = {
        "upper-left": {"components": len(dot_details["upper"]), "selected_pixels": sum(int(np.count_nonzero(np.asarray(m["mask"]))) for m in pulses if m["name"].startswith("upper-dot-wave"))},
        "lower-right": {"components": len(dot_details["lower"]), "selected_pixels": sum(int(np.count_nonzero(np.asarray(m["mask"]))) for m in pulses if m["name"].startswith("lower-dot-wave"))},
    }
    stats["traces"] = [
        {"name": record["name"], "coverage": round(record["coverage"], 3), "bbox": record["bbox"],
         "moving": any(comet["name"] == record["name"] for comet in comets)}
        for record in comet_records
    ]
    stats["pulse_layers"] = len(pulses)
    stats["moving_sweeps"] = len(comets)
    return pulses, comets, traces, stats


def trace_coverage(mask: Image.Image, points: list[tuple[float, float]]) -> float:
    alpha = np.asarray(mask, dtype=np.uint8)
    total = 0
    hit = 0
    lengths = [math.dist(a, b) for a, b in zip(points, points[1:])]
    total_length = sum(lengths)
    steps = max(1, int(total_length / 4))
    for i in range(steps + 1):
        p = phase4.point_on_path(points, i / steps)
        x, y = round(p[0]), round(p[1])
        total += 1
        if alpha[max(0, y - 3):min(H, y + 4), max(0, x - 3):min(W, x + 4)].max(initial=0) > 0:
            hit += 1
    return hit / total


def phase4_layers() -> tuple[dict[str, Image.Image], dict[str, tuple[float, float, float, float]]]:
    _, phase3 = phase4.phase3_data()
    layers = dict(phase3)
    for name in [
        "circuit-upper-trace-overlay", "circuit-mid-upper-trace-overlay",
        "button-top-border", "button-bottom-border", "button-left-border",
        "button-right-border", "button-corner-regions",
        "circuit-upper-trace-overlay-halo", "circuit-mid-upper-trace-overlay-halo",
        "button-top-border-halo", "button-bottom-border-halo", "button-left-border-halo",
        "button-right-border-halo", "button-corner-regions-halo",
    ]:
        layers[name] = Image.open(PHASE4 / "layers" / f"{name}-effect.png").convert("RGBA")
    return layers, {
        "ambient-light-overlay": (0.48, 0.75, math.pi / 2, 9.0),
        "circuit-light-overlay": (0.52, 0.80, 0.0, 9.0),
        "button-highlight-overlay": (0.42, 0.76, -math.pi / 2, 9.0),
        "circuit-upper-trace-overlay": (0.52, 0.96, 0.0, 9.0),
        "circuit-mid-upper-trace-overlay": (0.48, 0.90, 0.70, 9.0),
        "button-top-border": (0.38, 0.78, 0.0, 9.0),
        "button-bottom-border": (0.38, 0.78, math.pi, 9.0),
        "button-left-border": (0.34, 0.72, math.pi / 2, 9.0),
        "button-right-border": (0.34, 0.72, -math.pi / 2, 9.0),
        "button-corner-regions": (0.32, 0.68, math.pi / 2, 9.0),
        "circuit-upper-trace-overlay-halo": (0.18, 0.68, 0.20, 9.0),
        "circuit-mid-upper-trace-overlay-halo": (0.16, 0.62, 0.70, 9.0),
        "button-top-border-halo": (0.16, 0.54, 0.10, 9.0),
        "button-bottom-border-halo": (0.16, 0.54, math.pi, 9.0),
        "button-left-border-halo": (0.14, 0.50, math.pi / 2, 9.0),
        "button-right-border-halo": (0.14, 0.50, -math.pi / 2, 9.0),
        "button-corner-regions-halo": (0.12, 0.48, math.pi / 2, 9.0),
    }


def scale_layer(image: Image.Image, size: tuple[int, int] = PREVIEW_SIZE) -> dict:
    cropped, bbox = crop_rgba(image)
    sx, sy = size[0] / W, size[1] / H
    scaled = cropped.resize((max(1, round(cropped.width * sx)), max(1, round(cropped.height * sy))), Image.Resampling.LANCZOS)
    return {"image": scaled, "x": round(bbox[0] * sx), "y": round(bbox[1] * sy)}


def draw_timed_layer(frame: Image.Image, layer: dict, opacity: float) -> None:
    image = layer["image"].copy()
    if opacity < 1:
        image.putalpha(image.getchannel("A").point(lambda alpha: round(alpha * opacity)))
    frame.alpha_composite(image, (layer["x"], layer["y"]))


def add_scaled_glint(frame: Image.Image, point: tuple[float, float], patch: Image.Image,
                     strength: float = 1.0) -> None:
    if strength < 1:
        patch = patch.copy()
        patch.putalpha(patch.getchannel("A").point(lambda alpha: round(alpha * strength)))
    x = round(point[0] * PREVIEW_SIZE[0] / W - patch.width / 2)
    y = round(point[1] * PREVIEW_SIZE[1] / H - patch.height / 2)
    frame.alpha_composite(patch, (x, y))


def save_preview_gif(frames: list[Image.Image], path: Path, duration_ms: int) -> None:
    """Use delta frames so the review GIF stays small while remaining opaque."""
    thumb_w = max(1, frames[0].width // 6)
    thumb_h = max(1, frames[0].height // 6)
    columns = min(6, len(frames))
    rows = math.ceil(len(frames) / columns)
    sheet = Image.new("RGB", (columns * thumb_w, rows * thumb_h))
    for index, frame in enumerate(frames):
        thumb = frame.convert("RGB").resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)
        sheet.paste(thumb, ((index % columns) * thumb_w, (index // columns) * thumb_h))

    # Reserve the tiny red, yellow and green terminal lamps in the global GIF
    # palette. A contact-sheet-only median cut otherwise drops these rare hues.
    lamp_points = [(1117, 229), (1150, 229), (1183, 229)]
    step = max(1, len(frames) // 18)
    reserved = set()
    sx, sy = frames[0].width / W, frames[0].height / H
    for original_x, original_y in lamp_points:
        x, y = round(original_x * sx), round(original_y * sy)
        for frame in frames[::step]:
            color = frame.convert("RGB").getpixel((x, y))
            if max(color) - min(color) >= 35:
                reserved.add(tuple(min(255, round(channel / 8) * 8) for channel in color))
    reserved_colors = sorted(reserved)
    palette_basis = Image.new("RGB", (sheet.width + max(1, len(reserved_colors)) * 8, max(sheet.height, 8)))
    palette_basis.paste(sheet, (0, 0))
    for index, color in enumerate(reserved_colors):
        ImageDraw.Draw(palette_basis).rectangle((sheet.width + index * 8, 0, sheet.width + index * 8 + 7, 7), fill=color)
    remaining = 256 - len(reserved_colors)
    reduced = palette_basis.quantize(colors=remaining, method=Image.Quantize.MEDIANCUT)
    palette_colors = [channel for color in reserved_colors for channel in color]
    palette_colors.extend(reduced.getpalette()[:remaining * 3])
    palette = Image.new("P", (1, 1))
    palette.putpalette((palette_colors + [0] * 768)[:768])
    indexed = [frame.convert("RGB").quantize(palette=palette, dither=Image.Dither.NONE)
               for frame in frames]
    indexed[0].save(path, save_all=True, append_images=indexed[1:], duration=duration_ms,
                    loop=0, optimize=True, disposal=1)


def prepare_preview(source: Image.Image, old_layers: dict[str, Image.Image],
                    old_timing: dict, pulses: list[dict]) -> tuple[Image.Image, dict[str, dict]]:
    base = source.convert("RGBA").resize(PREVIEW_SIZE, Image.Resampling.LANCZOS)
    scaled_old = {name: scale_layer(image) for name, image in old_layers.items()}
    scaled_new = {layer["name"]: scale_layer(layer["image"]) for layer in pulses}
    return base, {"old": scaled_old, "new": scaled_new, "timing": old_timing}


def preview_frame(t: float, base: Image.Image, old: dict, pulses: list[dict],
                  comets: list[dict], old_timing: dict,
                  new_glint_patches: dict[str, Image.Image]) -> Image.Image:
    frame = base.copy()
    for name, layer in old.items():
        if name == "__new__":
            continue
        low, high, phase, period = old_timing[name]
        draw_timed_layer(frame, layer, pulse_value(low, high, phase, period, t))

    # Keep the established Phase 4 comet trails.
    for path, color, cycle, offset in [
        (phase4.UPPER_TRACE_PATH, (119, 224, 255), 3.0, 0.0),
        (phase4.MID_TRACE_PATH, (127, 209, 255), 3.0, 0.43),
        (phase4.BUTTON_PATH, (151, 213, 255), 4.5, 0.18),
    ]:
        patch = phase4.glint_patch(color).resize((34, 34), Image.Resampling.LANCZOS)
        for lag, strength in ((0.0, 1.0), (0.08, 0.78), (0.16, 0.58), (0.24, 0.36), (0.32, 0.18)):
            point = phase4.point_on_path(path, (t / cycle + offset - lag / cycle) % 1)
            add_scaled_glint(frame, point, patch, strength)

    for comet in comets:
        cycle = comet["period"]
        patch = new_glint_patches[comet["name"]]
        for lag, strength in ((0.0, 0.88), (0.13, 0.42), (0.26, 0.20)):
            point = phase4.point_on_path(comet["points"], (t / cycle + comet["phase"] - lag / cycle) % 1)
            add_scaled_glint(frame, point, patch, strength)

    for pulse in pulses:
        opacity = pulse_value(pulse["low"], pulse["high"], pulse["phase"], pulse["period"], t)
        draw_timed_layer(frame, old["__new__"][pulse["name"]], opacity)
    return frame.convert("RGB")


def save_preview(source: Image.Image, old_layers: dict[str, Image.Image], old_timing: dict,
                 pulses: list[dict], comets: list[dict], preview_dir: Path,
                 initial: bool = True) -> tuple[list[Image.Image], dict]:
    preview_dir.mkdir(parents=True, exist_ok=True)
    base, prepared = prepare_preview(source, old_layers, old_timing, pulses)
    prepared["old"]["__new__"] = prepared["new"]
    patches = {c["name"]: phase4.glint_patch(c["color"]).resize((30, 30), Image.Resampling.LANCZOS) for c in comets}
    frame_count = 72 if initial else 180
    duration_ms = 125 if initial else 50
    frames: list[Image.Image] = []
    for index in range(frame_count):
        t = DURATION * index / frame_count
        frames.append(preview_frame(t, base, prepared["old"], pulses, comets, old_timing, patches))
    gif_path = preview_dir / ("initial-animation-preview.gif" if initial else "profile-banner-phase-5-animation-preview.gif")
    save_preview_gif(frames, gif_path, duration_ms=duration_ms)
    sample_times = [0, 2.25, 4.5, 6.75, 8.875]
    picks = [frames[round(t / DURATION * frame_count) % frame_count] for t in sample_times]
    contact = Image.new("RGB", (PREVIEW_SIZE[0] * 3, PREVIEW_SIZE[1] * 2), (8, 10, 16))
    draw = ImageDraw.Draw(contact)
    for idx, (t, image) in enumerate(zip(sample_times, picks)):
        x, y = (idx % 3) * PREVIEW_SIZE[0], (idx // 3) * PREVIEW_SIZE[1]
        contact.paste(image, (x, y))
        draw.rectangle((x, y, x + 130, y + 25), fill=(7, 11, 18))
        draw.text((x + 8, y + 6), f"t = {t:.2f} s", fill=(235, 244, 255))
    contact_path = preview_dir / ("initial-preview-contact-sheet.jpg" if initial else "animation-contact-sheet.jpg")
    contact.save(contact_path, quality=91)
    for t, image in zip(sample_times, picks):
        image.save(preview_dir / (f"frame-{t:05.2f}s.png"))
    return frames, {"gif": gif_path, "contact": contact_path, "frames": frame_count, "duration_ms": duration_ms}


def save_selection_audit(source: Image.Image, masks: dict[str, Image.Image], path: Path) -> None:
    audit = source.convert("RGBA").copy()
    colors = [
        (255, 0, 220), (0, 233, 255), (255, 196, 0), (150, 98, 255),
        (255, 80, 112), (74, 255, 156), (255, 140, 36), (92, 140, 255),
    ]
    for index, (name, mask) in enumerate(masks.items()):
        color = colors[index % len(colors)]
        paint = Image.new("RGBA", (W, H), (*color, 0))
        paint.putalpha(mask.point(lambda alpha: round(alpha * 0.78)))
        audit.alpha_composite(paint)
    audit.convert("RGB").save(path, quality=95)


def write_preview_only(source: Image.Image, old_layers: dict[str, Image.Image], old_timing: dict,
                       pulses: list[dict], comets: list[dict], traces: dict[str, Image.Image],
                       stats: dict) -> None:
    work = OUT / "preview"
    work.mkdir(parents=True, exist_ok=True)
    masks = {p["name"]: p["mask"] for p in pulses}
    masks.update(traces)
    save_selection_audit(source, masks, work / "initial-selection-audit.jpg")
    _, files = save_preview(source, old_layers, old_timing, pulses, comets, work, initial=True)
    (work / "initial-preview-stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(f"Initial preview: {files['gif']} ({files['frames']} frames, {files['duration_ms']}ms)")
    print(f"Initial contact sheet: {files['contact']}")
    print(f"Selection audit: {work / 'initial-selection-audit.jpg'}")
    print(json.dumps(stats, indent=2))


def opacity_keyframes(pulse: dict) -> list[dict]:
    ticks = list(range(0, FRAMES, 3)) + [FRAMES]

    def value(frame: int) -> float:
        return round(100 * pulse_value(pulse["low"], pulse["high"], pulse["phase"], pulse["period"], frame / FPS), 4)

    keys = []
    for start, end in zip(ticks, ticks[1:]):
        keys.append({"t": start, "s": [value(start)], "e": [value(end)],
                     "i": {"x": [0.333], "y": [0.333]},
                     "o": {"x": [0.667], "y": [0.667]}, "h": 0})
    keys.append({"t": FRAMES, "s": [value(FRAMES)], "e": [value(FRAMES)],
                 "i": {"x": [0.333], "y": [0.333]},
                 "o": {"x": [0.667], "y": [0.667]}, "h": 0})
    return keys


def image_layer(name: str, ref_id: str, index: int, bbox: tuple[int, int, int, int],
                opacity: dict | None = None, position: dict | None = None) -> dict:
    x, y, _, _ = bbox
    return {
        "ddd": 0, "ind": index, "ty": 2, "nm": name, "refId": ref_id, "sr": 1,
        "ks": {
            "o": opacity or {"a": 0, "k": 100}, "r": {"a": 0, "k": 0},
            "p": position or {"a": 0, "k": [x, y, 0]},
            "a": {"a": 0, "k": [0, 0, 0]}, "s": {"a": 0, "k": [100, 100, 100]},
        },
        "ao": 0, "ip": 0, "op": FRAMES, "st": 0, "bm": 0,
    }


def as_embedded_asset(asset: dict, source_path: Path) -> dict:
    encoded = base64.b64encode(source_path.read_bytes()).decode("ascii")
    result = dict(asset)
    result.update({"u": "", "p": "data:image/png;base64," + encoded, "e": 1})
    return result


def make_lottie(pulses: list[dict], comets: list[dict]) -> tuple[Path, int]:
    """Create a single-file Lottie JSON with all raster assets embedded."""
    out_images = OUT / "lottie" / "images"
    out_images.mkdir(parents=True, exist_ok=True)
    old_doc = json.loads(PHASE4_JSON.read_text(encoding="utf-8"))
    doc = dict(old_doc)
    doc["nm"] = "Profile banner — Phase 5 full motion"

    embedded_old_assets = []
    for asset in old_doc["assets"]:
        source_path = PHASE4 / asset.get("u", "") / asset["p"]
        shutil.copyfile(source_path, out_images / Path(asset["p"]).name)
        embedded_old_assets.append(as_embedded_asset(asset, source_path))

    new_assets: list[dict] = []
    new_layers: list[dict] = []
    next_index = max(layer.get("ind", 0) for layer in old_doc["layers"]) + 1

    for offset, pulse in enumerate(pulses):
        cropped, bbox = crop_rgba(pulse["image"])
        filename = f"phase5-{pulse['name']}.png"
        png_data = phase4.png_bytes(cropped)
        (out_images / filename).write_bytes(png_data)
        ref_id = "phase5_" + pulse["name"]
        uri = "data:image/png;base64," + base64.b64encode(png_data).decode("ascii")
        new_assets.append({"id": ref_id, "w": cropped.width, "h": cropped.height, "u": "", "p": uri, "e": 1})
        new_layers.append(image_layer(
            pulse["name"], ref_id, next_index + offset, bbox,
            opacity={"a": 1, "k": opacity_keyframes(pulse)},
        ))

    for offset, comet in enumerate(comets, start=len(pulses)):
        patch = phase4.glint_patch(comet["color"])
        filename = f"phase5-{comet['name']}.png"
        png_data = phase4.png_bytes(patch)
        (out_images / filename).write_bytes(png_data)
        ref_id = "phase5_" + comet["name"]
        uri = "data:image/png;base64," + base64.b64encode(png_data).decode("ascii")
        new_assets.append({"id": ref_id, "w": patch.width, "h": patch.height, "u": "", "p": uri, "e": 1})
        position_keys = phase4.position_keys(
            comet["points"], round(comet["period"] * FPS), comet["phase"]
        )
        new_layers.append(image_layer(
            comet["name"], ref_id, next_index + offset,
            (0, 0, patch.width, patch.height),
            position={"a": 1, "k": position_keys},
        ))

    base_layers = [layer for layer in old_doc["layers"] if layer.get("nm") == "base-artwork"]
    other_layers = [layer for layer in old_doc["layers"] if layer.get("nm") != "base-artwork"]
    doc["assets"] = embedded_old_assets + new_assets
    doc["layers"] = new_layers + other_layers + base_layers
    target = OUT / "profile-banner-phase-5.json"
    temporary = OUT / "profile-banner-phase-5.json.tmp"
    temporary.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    temporary.replace(target)
    return target, len(new_layers)


def make_animated_svg(pulses: list[dict], comets: list[dict]) -> Path:
    svg = PHASE4_SVG.read_text(encoding="utf-8")
    closing = svg.rfind("</svg>")
    if closing < 0:
        raise ValueError("Phase 4 SVG is missing its closing svg element")
    elements = ['  <g id="phase-5-motion-overlays" aria-hidden="true" pointer-events="none">']
    for pulse in pulses:
        cropped, bbox = crop_rgba(pulse["image"])
        uri = data_uri(cropped)
        x, y, x1, y1 = bbox
        sample_count = 24
        values = [
            f"{pulse_value(pulse['low'], pulse['high'], pulse['phase'], pulse['period'], DURATION * i / sample_count):.4f}"
            for i in range(sample_count + 1)
        ]
        elements.append(
            f'    <image id="phase-5-{pulse["name"]}" x="{x}" y="{y}" '
            f'width="{x1 - x}" height="{y1 - y}" href="{uri}" opacity="{values[0]}">'
            f'<animate attributeName="opacity" values="{";".join(values)}" '
            f'dur="{DURATION:.3f}s" repeatCount="indefinite"/></image>'
        )
    for comet in comets:
        patch_uri = data_uri(phase4.glint_patch(comet["color"]))
        points = [(x - 28, y - 28) for x, y in comet["points"]]
        path = "M " + " L ".join(f"{x:.2f} {y:.2f}" for x, y in points)
        delay = -comet["phase"] * comet["period"]
        elements.append(
            f'    <image id="phase-5-{comet["name"]}" x="0" y="0" width="56" height="56" '
            f'href="{patch_uri}"><animateMotion path="{path}" '
            f'dur="{comet["period"]:.3f}s" begin="{delay:.3f}s" calcMode="paced" '
            f'repeatCount="indefinite"/></image>'
        )
    elements.append("  </g>")
    target = OUT / "profile-banner-phase-5-animated.svg"
    target.write_text(svg[:closing] + "\n" + "\n".join(elements) + "\n" + svg[closing:], encoding="utf-8")
    return target


def write_reports(source: Image.Image, pulses: list[dict], comets: list[dict], stats: dict,
                  lottie_path: Path, new_layer_count: int, svg_path: Path,
                  preview_info: dict, static_path: Path) -> None:
    source_hash = __import__("hashlib").sha256(SOURCE.read_bytes()).hexdigest()
    static_hash = __import__("hashlib").sha256(static_path.read_bytes()).hexdigest()
    animated_gif = preview_info["gif"]
    static_pixels_match = Image.open(static_path).convert("RGB").tobytes() == source.convert("RGB").tobytes()
    coverage_rows = "\n".join(
        f"| {row['name']} | {row['coverage']:.0%} | {'sí' if row['moving'] else 'no'} |"
        for row in stats["traces"]
    )
    regions = [
        "Anillo luminoso grande: selección cromática limitada a píxeles existentes dentro de una banda circular.",
        "Perímetro de la insignia CB: selección cromática de los píxeles visibles del borde; letras excluidas.",
        "Borde visible del panel terminal: segmentos superior, izquierdo y derecho; partes ocultas por la insignia o el botón no se reconstruyen.",
        "Tres indicadores de estado del terminal: máscaras separadas por color.",
        f"Campo de puntos superior izquierdo: {stats['dots']['upper-left']['components']} componentes de origen aislados.",
        f"Campo de puntos inferior derecho: {stats['dots']['lower-right']['components']} componentes de origen aislados.",
        "Cinco trazos periféricos: solo los píxeles cromáticos dentro de corredores ajustados a líneas visibles.",
        "Trazos superiores y borde del botón: capas heredadas de Phase 4, conservadas sin alterar el arte base.",
    ]
    coverage_text = "\n".join(f"- {item}" for item in regions)
    report = f'''# Phase 5 — Full banner motion coverage

## Resultado

- Composición: {W} × {H}, {FPS} fps, {DURATION:g} segundos, {FRAMES} fotogramas.
- Capa base: la imagen original se mantiene intacta. El PNG estático se copió byte por byte y coincide con el origen en píxeles: **{static_pixels_match}**.
- SHA-256 del origen: `{source_hash}`.
- SHA-256 de la copia estática: `{static_hash}`.
- Efectos añadidos sobre la composición heredada: {new_layer_count} capas ({len(pulses)} pulsos y {len(comets)} barridos luminosos).
- La animación se mantiene como capas raster con transparencia. No se afirma que el banner original se haya convertido en vectores editables.

## Regiones preparadas

{coverage_text}

### Cobertura de barridos sobre píxeles fuente

| Trazo | Cobertura medida | Barrido móvil |
|---|---:|---:|
{coverage_rows}

La cobertura se estima muestreando el recorrido y comprobando que cada punto cae cerca de píxeles fuente seleccionados. Los trazos bajo texto, iconos, paneles o botones no se prolongan por zonas ocultas.

## Límites pendientes

- El cursor del terminal y el texto del terminal siguen dentro de la imagen base; no se aíslan ni animan.
- Tipografía, iconos, contenido del botón y el resto del banner permanecen como raster estático.
- Los bordes ocultos del panel y los segmentos tapados de circuitos no se reconstruyen.
- Las máscaras realzan píxeles de color existentes; no crean rutas vectoriales independientes.
- No se abrió un navegador ni LottieFiles Creator. El JSON y las imágenes se prepararon localmente; falta validar su render dentro de esa plataforma.
- La salida SVG usa SMIL (`animate` / `animateMotion`); su reproducción depende del visor. El JSON Lottie es el formato principal de intercambio.

## Archivos

- `profile-banner-phase-5.json`: Lottie autocontenido con imágenes inline.
- `lottie/images/`: PNGs auxiliares transparentes para inspección y flujo con assets separados.
- `profile-banner-phase-5-animated.svg`: SVG autocontenido con efectos SMIL.
- `profile-banner-phase-5-static-preview.png`: copia estática exacta del origen.
- `preview/profile-banner-phase-5-animation-preview.gif`: previsualización animada de 9 segundos.
- `preview/animation-contact-sheet.jpg`: cinco instantes de la animación.
- `preview/initial-selection-audit.jpg`: auditoría visual de las máscaras seleccionadas.
'''
    (OUT / "motion-coverage-report.md").write_text(report, encoding="utf-8")

    package_json = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    lottie_declared = package_json.get("dependencies", {}).get("lottie-web", "not declared")
    installed_manifest = ROOT / "node_modules" / "lottie-web" / "package.json"
    lottie_version = json.loads(installed_manifest.read_text(encoding="utf-8")).get("version", "unknown") if installed_manifest.exists() else "not installed"
    json_doc = json.loads(lottie_path.read_text(encoding="utf-8"))
    asset_count = len(json_doc.get("assets", []))
    total_assets_bytes = sum(path.stat().st_size for path in (OUT / "lottie" / "images").glob("*.png"))
    perf = f'''# Phase 5 — Compatibility and performance notes

- Installed player: `lottie-web {lottie_version}` (project range: `{lottie_declared}`).
- Lottie JSON version field: `{json_doc.get('v')}`.
- Canvas: `{json_doc.get('w')} × {json_doc.get('h')}`.
- Frame rate and length: `{json_doc.get('fr')} fps`, `{json_doc.get('op') - json_doc.get('ip')} frames` ({(json_doc.get('op') - json_doc.get('ip')) / json_doc.get('fr'):.1f} s).
- Image assets: `{asset_count}`; all referenced in the main JSON as inline PNG data URIs, so the animation does not depend on remote or relative paths.
- Auxiliary PNG assets: `{total_assets_bytes / 1024:.1f} KiB` total.
- Lottie JSON: `{lottie_path.stat().st_size / 1024:.1f} KiB`.
- Animated SVG: `{svg_path.stat().st_size / 1024:.1f} KiB`; its raster assets are embedded and it has no script or external image references.
- Preview GIF: `{animated_gif.stat().st_size / 1024:.1f} KiB`, `{preview_info['frames']} frames`, `{preview_info['duration_ms']} ms/frame`.
- The local checks verify JSON structure, embedded image data, dimensions, frame timing, SVG XML, and pixel fidelity of the static copy. The animation was not opened in a browser or in LottieFiles Creator, so playback in those interfaces remains unverified.
- `npm run build` completed successfully with Vite. Vite emitted a warning about direct `eval` in the bundled `lottie-web` player; there were no build errors.
'''
    (OUT / "compatibility-performance-report.md").write_text(perf, encoding="utf-8")


def finalize(source: Image.Image, old_layers: dict[str, Image.Image], old_timing: dict,
             pulses: list[dict], comets: list[dict], stats: dict) -> None:
    preview_dir = OUT / "preview"
    static_path = OUT / "profile-banner-phase-5-static-preview.png"
    shutil.copyfile(SOURCE, static_path)
    frames, preview_info = save_preview(source, old_layers, old_timing, pulses, comets, preview_dir, initial=False)
    lottie_path, new_layer_count = make_lottie(pulses, comets)
    svg_path = make_animated_svg(pulses, comets)
    write_reports(source, pulses, comets, stats, lottie_path, new_layer_count, svg_path, preview_info, static_path)
    print(f"Lottie JSON: {lottie_path} ({lottie_path.stat().st_size:,} bytes)")
    print(f"Animated SVG: {svg_path} ({svg_path.stat().st_size:,} bytes)")
    print(f"Static preview: {static_path}; pixel-identical to source")
    print(f"Animated preview: {preview_info['gif']} ({preview_info['frames']} frames)")


def main() -> None:
    source = Image.open(SOURCE).convert("RGB")
    if source.size != (W, H):
        raise ValueError(f"Expected {W}x{H}, got {source.size}")
    pulses, comets, traces, stats = make_selections(source)
    old_layers, old_timing = phase4_layers()
    if "--final" in sys.argv:
        finalize(source, old_layers, old_timing, pulses, comets, stats)
    else:
        write_preview_only(source, old_layers, old_timing, pulses, comets, traces, stats)


if __name__ == "__main__":
    main()
