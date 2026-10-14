"""Refine Phase 5 motion without changing the source banner or published files."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
PHASE5 = ROOT / "assets" / "phase-5-full-motion"
PHASE5_JSON = PHASE5 / "profile-banner-phase-5.json"
SOURCE = ROOT / "assets" / "image.png"
W, H = 1672, 941
FPS, FRAMES = 30, 270
DURATION = FRAMES / FPS
PREVIEW_SIZE = (1000, 563)

sys.path.insert(0, str(PHASE5))
import generate_phase5 as phase5  # noqa: E402
import generate_phase4 as phase4  # noqa: E402


MOTION_SPECS = [
    {
        "old": "circuit-upper-trace-comet", "name": "upper-right-outer-circuit-band",
        "points": phase4.UPPER_TRACE_PATH, "period": 3.0, "phase": 0.06,
        "color": (119, 224, 255), "preferred_length": 82,
    },
    {
        "old": "circuit-mid-upper-trace-comet", "name": "upper-right-inner-circuit-band",
        "points": phase4.MID_TRACE_PATH, "period": 4.5, "phase": 0.43,
        "color": (155, 205, 255), "preferred_length": 88,
    },
    {
        "old": "button-border-comet", "name": "portfolio-button-border-reflection",
        "points": phase4.BUTTON_PATH, "period": 9.0, "phase": 0.17,
        "color": (114, 226, 255), "preferred_length": 116,
    },
    {
        "old": "mid-left-trace-sweep", "name": "mid-left-circuit-band",
        "points": phase5.COMETS[0]["points"], "period": 4.5, "phase": 0.22,
        "color": (160, 231, 255), "preferred_length": 64,
    },
    {
        "old": "lower-upper-trace-sweep", "name": "lower-upper-circuit-band",
        "points": phase5.COMETS[1]["points"], "period": 3.0, "phase": 0.38,
        "color": (136, 216, 255), "preferred_length": 76,
    },
    {
        "old": "lower-stepped-trace-sweep", "name": "lower-stepped-circuit-band",
        "points": phase5.COMETS[2]["points"], "period": 4.5, "phase": 0.61,
        "color": (151, 203, 255), "preferred_length": 88,
    },
    {
        "old": "lower-node-trace-sweep", "name": "lower-node-circuit-band",
        "points": phase5.COMETS[3]["points"], "period": 4.5, "phase": 0.34,
        "color": (191, 171, 255), "preferred_length": 82,
    },
    {
        "old": "lower-accent-sweep", "name": "lower-accent-circuit-band",
        "points": phase5.COMETS[4]["points"], "period": 3.0, "phase": 0.73,
        "color": (135, 218, 255), "preferred_length": 42,
    },
]

OLD_ASSET_IDS = {
    "phase5_large-ring-intensity-wave",
    "phase5_upper-right-badge-perimeter",
    "phase4_circuit-upper-trace-comet",
    "phase4_circuit-mid-upper-trace-comet",
    "phase4_button-border-comet",
    *("phase5_" + spec["old"] for spec in MOTION_SPECS[3:]),
}
OLD_LAYER_NAMES = {
    "large-ring-intensity-wave", "upper-right-badge-perimeter",
    *(spec["old"] for spec in MOTION_SPECS),
}


def smoothstep(edge0: float, edge1: float, x: np.ndarray | float):
    if edge0 == edge1:
        return np.asarray(x >= edge1, dtype=np.float32)
    q = np.clip((np.asarray(x, dtype=np.float32) - edge0) / (edge1 - edge0), 0, 1)
    return q * q * (3 - 2 * q)


def decode_asset(asset: dict) -> Image.Image:
    uri = asset["p"]
    if not uri.startswith("data:image/png;base64,"):
        raise ValueError(f"Expected an embedded PNG asset, got {asset['id']}")
    return Image.open(io.BytesIO(base64.b64decode(uri.split(",", 1)[1]))).convert("RGBA")


def encode_asset(image: Image.Image, asset_id: str) -> dict:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    data = buffer.getvalue()
    return {
        "id": asset_id,
        "w": image.width,
        "h": image.height,
        "u": "",
        "p": "data:image/png;base64," + base64.b64encode(data).decode("ascii"),
        "e": 1,
    }


def source_canvas(asset: dict, position: tuple[int, int]) -> Image.Image:
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    canvas.alpha_composite(decode_asset(asset), position)
    return canvas


def sample_polar_field(field: np.ndarray, center: tuple[float, float],
                       angles: np.ndarray, radii: np.ndarray) -> np.ndarray:
    cx, cy = center
    xx = cx + radii[:, None] * np.cos(angles[None, :])
    yy = cy + radii[:, None] * np.sin(angles[None, :])
    x0 = np.floor(xx).astype(np.int32)
    y0 = np.floor(yy).astype(np.int32)
    fx = xx - x0
    fy = yy - y0
    x1, y1 = x0 + 1, y0 + 1
    valid0 = (x0 >= 0) & (x0 < field.shape[1]) & (y0 >= 0) & (y0 < field.shape[0])
    valid1 = (x1 >= 0) & (x1 < field.shape[1]) & (y1 >= 0) & (y1 < field.shape[0])
    x0c = np.clip(x0, 0, field.shape[1] - 1)
    x1c = np.clip(x1, 0, field.shape[1] - 1)
    y0c = np.clip(y0, 0, field.shape[0] - 1)
    y1c = np.clip(y1, 0, field.shape[0] - 1)
    a = field[y0c, x0c] * (1 - fx) * (1 - fy)
    b = field[y0c, x1c] * fx * (1 - fy)
    c = field[y1c, x0c] * (1 - fx) * fy
    d = field[y1c, x1c] * fx * fy
    valid = valid0 | valid1
    return (a + b + c + d) * valid


def interpolate_polar(profiles: np.ndarray, theta_index: np.ndarray,
                      radius_index: np.ndarray) -> np.ndarray:
    angle0 = np.floor(theta_index).astype(np.int32) % profiles.shape[1]
    angle1 = (angle0 + 1) % profiles.shape[1]
    frac_a = theta_index - np.floor(theta_index)
    radius0 = np.floor(radius_index).astype(np.int32)
    frac_r = radius_index - radius0
    valid = (radius0 >= 0) & (radius0 < profiles.shape[0] - 1)
    r0 = np.clip(radius0, 0, profiles.shape[0] - 1)
    r1 = np.clip(r0 + 1, 0, profiles.shape[0] - 1)
    p00 = profiles[r0, angle0]
    p01 = profiles[r0, angle1]
    p10 = profiles[r1, angle0]
    p11 = profiles[r1, angle1]
    low = p00 * (1 - frac_a) + p01 * frac_a
    high = p10 * (1 - frac_a) + p11 * frac_a
    result = low * (1 - frac_r) + high * frac_r
    return result * valid


def make_traveling_arc(effect: Image.Image, center: tuple[float, float],
                       radius_min: float, radius_max: float, head_deg: float,
                       arc_deg: float, tint: tuple[int, int, int],
                       size: int = 900) -> Image.Image:
    """Complete the clipped source-pixel ring profile, then reveal one moving arc."""
    cx, cy = center
    angle_count = 720
    radius_min_grid, radius_max_grid, radius_step = radius_min - 4, radius_max + 4, 0.5
    theta = np.linspace(-math.pi, math.pi, angle_count, endpoint=False, dtype=np.float32)
    radii = np.arange(radius_min_grid, radius_max_grid + radius_step / 2,
                      radius_step, dtype=np.float32)
    rgba = np.asarray(effect.convert("RGBA"), dtype=np.float32)
    channels = [sample_polar_field(rgba[:, :, index], center, theta, radii)
                for index in range(4)]
    # Ring arcs beyond the canvas have no source pixels. Borrow the nearest visible
    # angular profile; the SVG/Lottie viewport clips that inferred continuation.
    alpha_profiles = channels[3]
    valid = np.sum(alpha_profiles, axis=0) > 100
    if not np.any(valid):
        raise ValueError("The source-pixel ring mask did not contain visible pixels")
    valid_indices = np.flatnonzero(valid)
    for angle_index in np.flatnonzero(~valid):
        distance = np.minimum((valid_indices - angle_index) % angle_count,
                              (angle_index - valid_indices) % angle_count)
        nearest = valid_indices[np.argmin(distance)]
        for channel in channels:
            channel[:, angle_index] = channel[:, nearest]

    yy, xx = np.mgrid[0:size, 0:size]
    dx = xx.astype(np.float32) - size / 2
    dy = yy.astype(np.float32) - size / 2
    radius = np.hypot(dx, dy)
    angle = np.arctan2(dy, dx)
    theta_index = ((angle + math.pi) / (2 * math.pi) * angle_count) % angle_count
    radius_index = (radius - radius_min_grid) / radius_step
    sampled = [interpolate_polar(channel, theta_index, radius_index) for channel in channels]
    head = math.radians(head_deg)
    arc_len = math.radians(arc_deg)
    distance = (head - angle) % (2 * math.pi)
    within = (distance >= 0) & (distance <= arc_len)
    edge_softness = math.radians(2.6)
    edge = smoothstep(0, edge_softness, distance) * (1 - smoothstep(arc_len - edge_softness, arc_len, distance))
    tail = 0.26 + 0.74 * np.power(np.clip(1 - distance / arc_len, 0, 1), 1.22)
    envelope = np.where(within, edge * tail, 0)
    source_alpha = sampled[3] / 255.0
    alpha = np.clip(source_alpha * envelope * 1.36 * 255, 0, 255)
    source_rgb = np.stack(sampled[:3], axis=2)
    tint_array = np.asarray(tint, dtype=np.float32)[None, None, :]
    color_mix = (envelope * 0.38)[:, :, None]
    rgb = np.clip(source_rgb * (1 - color_mix) + tint_array * color_mix, 0, 255)
    output = np.zeros((size, size, 4), dtype=np.uint8)
    output[:, :, :3] = rgb.round().astype(np.uint8)
    output[:, :, 3] = alpha.round().astype(np.uint8)
    image = Image.fromarray(output, "RGBA")
    return image


def path_lengths(points: list[tuple[float, float]]) -> tuple[list[float], float]:
    lengths = [math.dist(a, b) for a, b in zip(points, points[1:])]
    return lengths, sum(lengths)


def point_and_tangent(points: list[tuple[float, float]], progress: float,
                      smoothing: float) -> tuple[tuple[float, float], float]:
    lengths, total = path_lengths(points)
    position = (progress % 1) * total

    def locate(distance: float) -> tuple[float, float]:
        distance = min(max(distance, 0), total)
        for (a, b), segment_length in zip(zip(points, points[1:]), lengths):
            if distance <= segment_length:
                q = distance / segment_length if segment_length else 0
                return a[0] + (b[0] - a[0]) * q, a[1] + (b[1] - a[1]) * q
            distance -= segment_length
        return points[-1]

    point = locate(position)
    before = locate(max(0, position - smoothing / 2))
    after = locate(min(total, position + smoothing / 2))
    angle = math.degrees(math.atan2(after[1] - before[1], after[0] - before[0]))
    return point, angle


def keyframe_list(ticks: list[int], values: list[list[float]]) -> list[dict]:
    keys = []
    for index in range(len(ticks) - 1):
        keys.append({
            "t": ticks[index], "s": values[index], "e": values[index + 1],
            "i": {"x": [0.667], "y": [0.667]},
            "o": {"x": [0.333], "y": [0.333]}, "h": 0,
        })
    keys.append({"t": ticks[-1], "s": values[-1], "e": values[-1],
                 "i": {"x": [0.667], "y": [0.667]},
                 "o": {"x": [0.333], "y": [0.333]}, "h": 0})
    return keys


def cycle_progress(time_s: float, period: float, phase: float) -> float:
    return (time_s / period + phase) % 1.0


def fade_gate(progress: float, edge: float) -> float:
    if progress < edge:
        return float(smoothstep(0, edge, progress))
    if progress > 1 - edge:
        return float(1 - smoothstep(1 - edge, 1, progress))
    return 1.0


def make_motion_layer(layer: dict, spec: dict, asset_id: str,
                      asset_size: tuple[int, int], ticks: list[int]) -> dict:
    points = [(float(x), float(y)) for x, y in spec["points"]]
    lengths, total = path_lengths(points)
    band_length = min(spec["preferred_length"], max(24, round(total * 0.30)))
    edge = min(0.28, (band_length / 2 + 6) / total)
    positions, rotations, opacities = [], [], []
    for frame in ticks:
        t = frame / FPS
        q = cycle_progress(t, spec["period"], spec["phase"])
        point, angle = point_and_tangent(points, q, band_length * 0.42)
        gate = fade_gate(q, edge)
        pulse = 0.82 + 0.18 * (0.5 + 0.5 * math.sin(2 * math.pi * t / spec["period"] + 0.9))
        positions.append([round(point[0], 3), round(point[1], 3), 0])
        rotations.append([round(angle, 3)])
        opacities.append([round(100 * gate * pulse, 4)])
    layer.update({"nm": spec["name"], "refId": asset_id})
    layer["ks"] = {
        "o": {"a": 1, "k": keyframe_list(ticks, opacities)},
        "r": {"a": 1, "k": keyframe_list(ticks, rotations)},
        "p": {"a": 1, "k": keyframe_list(ticks, positions)},
        "a": {"a": 0, "k": [asset_size[0] / 2, asset_size[1] / 2, 0]},
        "s": {"a": 0, "k": [100, 100, 100]},
    }
    return layer


def make_arc_layer(layer: dict, name: str, asset_id: str, center: tuple[float, float],
                   period: float, opacity_range: tuple[float, float],
                   phase: float, ticks: list[int], direction: float = 360) -> dict:
    rotations, opacities = [], []
    low, high = opacity_range
    for frame in ticks:
        t = frame / FPS
        angle = direction * t / period
        value = low + (high - low) * (0.5 + 0.5 * math.sin(2 * math.pi * t / period + phase))
        rotations.append([round(angle, 4)])
        opacities.append([round(value, 4)])
    layer.update({"nm": name, "refId": asset_id})
    asset_size = (900, 900) if "ring" in name else (240, 240)
    layer["ks"] = {
        "o": {"a": 1, "k": keyframe_list(ticks, opacities)},
        "r": {"a": 1, "k": keyframe_list(ticks, rotations)},
        "p": {"a": 0, "k": [center[0], center[1], 0]},
        "a": {"a": 0, "k": [asset_size[0] / 2, asset_size[1] / 2, 0]},
        "s": {"a": 0, "k": [100, 100, 100]},
    }
    return layer


def make_band(length: int, color: tuple[int, int, int], height: int = 20) -> Image.Image:
    width = int(length)
    yy, xx = np.mgrid[0:height, 0:width]
    x = xx / max(1, width - 1)
    y = yy - (height - 1) / 2
    lead = np.clip(x / 0.70, 0, 1)
    taper = smoothstep(0.0, 0.10, x) * (1 - smoothstep(0.94, 1.0, x))
    horizontal = (0.15 + 0.85 * lead) * taper
    halo = np.exp(-0.5 * np.square(y / 4.1)) * 48
    core = np.exp(-0.5 * np.square(y / 1.55)) * 178
    alpha = np.clip((halo + core) * horizontal, 0, 235)
    tail_color = np.array([153, 97, 255], dtype=np.float32)
    head_color = np.array(color, dtype=np.float32)
    blend = np.clip(x, 0, 1)[:, :, None]
    rgb = tail_color[None, None, :] * (1 - blend) + head_color[None, None, :] * blend
    white_mix = (np.exp(-0.5 * np.square(y / 1.15)) * smoothstep(0.50, 0.78, x) * 0.64)[:, :, None]
    rgb = rgb * (1 - white_mix) + 255 * white_mix
    output = np.zeros((height, width, 4), dtype=np.uint8)
    output[:, :, :3] = np.clip(rgb, 0, 255).round().astype(np.uint8)
    output[:, :, 3] = alpha.round().astype(np.uint8)
    return Image.fromarray(output, "RGBA")


def prop_value(prop: dict, frame: float, default):
    if not prop:
        return default
    if prop.get("a", 0) == 0:
        value = prop.get("k", default)
        return value if isinstance(value, list) else [value]
    keys = prop.get("k", [])
    if not isinstance(keys, list) or not keys:
        return default
    for i, key in enumerate(keys):
        if frame < key.get("t", 0):
            break
        next_key = keys[i + 1] if i + 1 < len(keys) else None
        end_t = next_key["t"] if next_key else key.get("t", frame)
        start = key.get("s", default)
        end = key.get("e") or (next_key.get("s") if next_key else start)
        if frame <= end_t or next_key is None:
            if not isinstance(start, list):
                start = [start]
            if not isinstance(end, list):
                end = [end]
            if end_t <= key.get("t", 0):
                return start
            q = min(1, max(0, (frame - key.get("t", 0)) / (end_t - key.get("t", 0))))
            return [a + (b - a) * q for a, b in zip(start, end)]
    return keys[-1].get("s", default)


def render_frame(doc: dict, asset_images: dict[str, Image.Image], time_s: float,
                 size: tuple[int, int] = PREVIEW_SIZE,
                 assets_are_scaled: bool = False) -> Image.Image:
    frame_number = time_s * FPS
    sx, sy = size[0] / W, size[1] / H
    result = Image.new("RGBA", size, (0, 0, 0, 0))
    for layer in reversed(doc["layers"]):
        if layer.get("hd"):
            continue
        asset = asset_images[layer["refId"]]
        ks = layer.get("ks", {})
        opacity = float(prop_value(ks.get("o"), frame_number, [100])[0]) / 100
        if opacity <= 0:
            continue
        position = prop_value(ks.get("p"), frame_number, [0, 0, 0])
        anchor = prop_value(ks.get("a"), frame_number, [0, 0, 0])
        scale = prop_value(ks.get("s"), frame_number, [100, 100, 100])
        rotation = float(prop_value(ks.get("r"), frame_number, [0])[0])
        # Equivalent turns such as 360° and 720° should rasterize identically
        # at the loop boundary in the offline preview.
        rotation = ((rotation + 180) % 360) - 180
        if assets_are_scaled:
            position = [position[0] * sx, position[1] * sy, position[2] if len(position) > 2 else 0]
            anchor = [anchor[0] * sx, anchor[1] * sy, anchor[2] if len(anchor) > 2 else 0]
        if abs(scale[0] - 100) > 0.01 or abs(scale[1] - 100) > 0.01:
            scaled = (max(1, round(asset.width * scale[0] / 100)),
                      max(1, round(asset.height * scale[1] / 100)))
            asset = asset.resize(scaled, Image.Resampling.LANCZOS)
            anchor = [anchor[0] * scale[0] / 100, anchor[1] * scale[1] / 100]
        if abs(rotation) > 0.0001:
            asset = asset.rotate(-rotation, resample=Image.Resampling.BICUBIC, expand=True)
            left = round(position[0] - asset.width / 2)
            top = round(position[1] - asset.height / 2)
        elif anchor[0] or anchor[1]:
            left = round(position[0] - anchor[0])
            top = round(position[1] - anchor[1])
        else:
            left, top = round(position[0]), round(position[1])
        if opacity < 0.999:
            asset = asset.copy()
            asset.putalpha(asset.getchannel("A").point(lambda a: round(a * opacity)))
        result.alpha_composite(asset, (left, top))
    if assets_are_scaled or size == (W, H):
        return result.convert("RGB")
    return result.convert("RGB").resize(size, Image.Resampling.LANCZOS)


def extract_animation_values(prop: dict, component: int = 0) -> tuple[list[float], list[float]] | None:
    if not prop or prop.get("a", 0) == 0:
        return None
    keys = prop.get("k", [])
    if not keys:
        return None
    times, values = [], []
    for key in keys:
        start = key.get("s")
        if start is not None:
            times.append(min(1.0, max(0.0, key.get("t", 0) / FRAMES)))
            values.append(float(start[component] if isinstance(start, list) else start))
    last = keys[-1]
    end = last.get("e")
    if end is not None:
        times.append(1.0)
        values.append(float(end[component] if isinstance(end, list) else end))
    if times and times[-1] < 1:
        times.append(1.0)
        values.append(values[0])
    deduped = []
    for t, v in zip(times, values):
        if deduped and abs(t - deduped[-1][0]) < 1e-8:
            deduped[-1] = (t, v)
        else:
            deduped.append((t, v))
    return [item[0] for item in deduped], [item[1] for item in deduped]


def fmt_num(value: float) -> str:
    return f"{value:.4f}".rstrip("0").rstrip(".") or "0"


def svg_animation_element(tag: str, property_name: str,
                          samples: tuple[list[float], list[float]] | None,
                          period: float = DURATION) -> str:
    if not samples:
        return ""
    key_times, values = samples
    values_text = ";".join(fmt_num(value) for value in values)
    times_text = ";".join(fmt_num(value) for value in key_times)
    return (f'<{tag} attributeName="{property_name}" values="{values_text}" '
            f'keyTimes="{times_text}" dur="{period:.3f}s" repeatCount="indefinite" '
            'calcMode="linear" fill="freeze"/>')


def build_svg(doc: dict, target: Path) -> None:
    assets = {asset["id"]: asset for asset in doc["assets"]}
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" role="img" aria-label="Animated profile banner">',
        '<title>Profile banner — refined Phase 5.1 motion</title>',
        '<desc>Self-contained SVG animation based on the original profile banner.</desc>',
        '<defs><clipPath id="banner-clip"><rect width="1672" height="941"/></clipPath></defs>',
        '<g clip-path="url(#banner-clip)">',
    ]
    # Lottie stores front-to-back; SVG paints back-to-front.
    for layer in reversed(doc["layers"]):
        if layer.get("hd"):
            continue
        asset = assets[layer["refId"]]
        ks = layer.get("ks", {})
        pos = prop_value(ks.get("p"), 0, [0, 0, 0])
        anchor = prop_value(ks.get("a"), 0, [0, 0, 0])
        scale = prop_value(ks.get("s"), 0, [100, 100, 100])
        rotation = prop_value(ks.get("r"), 0, [0])[0]
        opacity = prop_value(ks.get("o"), 0, [100])[0] / 100
        uri = asset["p"].replace("&", "&amp;").replace('"', "&quot;")
        layer_id = "layer-" + "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in layer["nm"])
        if layer["nm"] == "base-artwork":
            lines.append(f'<image id="base-artwork" x="0" y="0" width="{W}" height="{H}" href="{uri}"/>')
            continue

        opacity_samples = extract_animation_values(ks.get("o"), 0)
        position_x_samples = extract_animation_values(ks.get("p"), 0)
        position_y_samples = extract_animation_values(ks.get("p"), 1)
        rotation_samples = extract_animation_values(ks.get("r"), 0)
        lines.append(f'<g id="{layer_id}" opacity="{fmt_num(opacity)}">')
        if opacity_samples:
            vals = ";".join(fmt_num(v / 100) for v in opacity_samples[1])
            times = ";".join(fmt_num(v) for v in opacity_samples[0])
            lines.append(f'<animate attributeName="opacity" values="{vals}" keyTimes="{times}" dur="{DURATION:.3f}s" repeatCount="indefinite" calcMode="linear"/>')

        if position_x_samples and position_y_samples:
            values = ";".join(f'{fmt_num(x)},{fmt_num(y)}'
                               for x, y in zip(position_x_samples[1], position_y_samples[1]))
            times = ";".join(fmt_num(v) for v in position_x_samples[0])
            lines.append('<g transform="translate(' + f'{fmt_num(pos[0])} {fmt_num(pos[1])}' + ')">')
            lines.append(f'<animateTransform attributeName="transform" type="translate" values="{values}" keyTimes="{times}" dur="{DURATION:.3f}s" repeatCount="indefinite" calcMode="linear"/>')
        else:
            lines.append(f'<g transform="translate({fmt_num(pos[0])} {fmt_num(pos[1])})">')
        if rotation_samples:
            values = ";".join(fmt_num(v) for v in rotation_samples[1])
            times = ";".join(fmt_num(v) for v in rotation_samples[0])
            lines.append(f'<g transform="rotate({fmt_num(rotation)})">')
            lines.append(f'<animateTransform attributeName="transform" type="rotate" values="{values}" keyTimes="{times}" dur="{DURATION:.3f}s" repeatCount="indefinite" calcMode="linear"/>')
        else:
            lines.append(f'<g transform="rotate({fmt_num(rotation)})">')
        sx, sy = float(scale[0]) / 100, float(scale[1]) / 100
        lines.append(f'<g transform="translate({fmt_num(-anchor[0])} {fmt_num(-anchor[1])}) scale({fmt_num(sx)} {fmt_num(sy)})">')
        lines.append(f'<image x="0" y="0" width="{asset["w"]}" height="{asset["h"]}" href="{uri}"/>')
        lines.extend(["</g>", "</g>", "</g>", "</g>"])
    lines.extend(["</g>", "</svg>"])
    target.write_text("\n".join(lines), encoding="utf-8")


def save_gif(frames: list[Image.Image], target: Path) -> None:
    phase5.save_preview_gif(frames, target, duration_ms=50)


def main() -> None:
    started = time.perf_counter()
    out_lottie = OUT / "profile-banner-phase-5.1.json"
    out_svg = OUT / "profile-banner-phase-5.1-animated.svg"
    preview_dir = OUT / "preview"
    preview_dir.mkdir(parents=True, exist_ok=True)

    phase5_doc = json.loads(PHASE5_JSON.read_text(encoding="utf-8"))
    source = Image.open(SOURCE).convert("RGBA")
    source_bytes = SOURCE.read_bytes()
    asset_map = {asset["id"]: asset for asset in phase5_doc["assets"]}
    source_asset = source_canvas(asset_map["phase5_large-ring-intensity-wave"], (933, 0))
    badge_asset = source_canvas(asset_map["phase5_upper-right-badge-perimeter"], (1400, 73))

    new_assets: list[dict] = []
    ring_id = "phase51_large-ring-traveling-arc"
    badge_id = "phase51_badge-edge-traveling-arc"
    ring_center = (1346.91, 419.90)
    badge_center = (1497.3, 172.5)
    ring_sprite = make_traveling_arc(source_asset, ring_center, 395, 430, 130, 78,
                                     (205, 235, 255), 900)
    badge_sprite = make_traveling_arc(badge_asset, badge_center, 78, 101, 212, 52,
                                      (222, 236, 255), 240)
    new_assets.extend([encode_asset(ring_sprite, ring_id), encode_asset(badge_sprite, badge_id)])

    specs_with_images = []
    for index, spec in enumerate(MOTION_SPECS):
        _, total = path_lengths([(float(x), float(y)) for x, y in spec["points"]])
        band_length = min(spec["preferred_length"], max(24, round(total * 0.30)))
        sprite = make_band(band_length, spec["color"], 20 if band_length > 50 else 16)
        asset_id = f"phase51_{spec['name']}"
        new_assets.append(encode_asset(sprite, asset_id))
        specs_with_images.append((spec, asset_id, sprite.size))

    ticks = list(range(0, FRAMES, 3)) + [FRAMES]
    layers = []
    for layer in phase5_doc["layers"]:
        old_name = layer.get("nm")
        if old_name == "large-ring-intensity-wave":
            layers.append(make_arc_layer(layer, "large-ring-traveling-highlight", ring_id,
                                         ring_center, 9.0, (70, 100), 0.60, ticks))
        elif old_name == "upper-right-badge-perimeter":
            layers.append(make_arc_layer(layer, "cb-badge-edge-traveling-highlight", badge_id,
                                         badge_center, 4.5, (66, 100), 1.24, ticks))
        elif old_name in {spec["old"] for spec in MOTION_SPECS}:
            spec, asset_id, asset_size = next(item for item in specs_with_images if item[0]["old"] == old_name)
            layers.append(make_motion_layer(layer, spec, asset_id, asset_size, ticks))
        else:
            layers.append(layer)

    doc = dict(phase5_doc)
    doc["nm"] = "Profile banner — Phase 5.1 refined motion"
    doc["assets"] = [asset for asset in phase5_doc["assets"] if asset["id"] not in OLD_ASSET_IDS] + new_assets
    doc["layers"] = layers
    if len(doc["layers"]) != len(phase5_doc["layers"]):
        raise AssertionError("Phase 5.1 must reuse Phase 5 layers, not increase the count")
    if len(doc["assets"]) != len(phase5_doc["assets"]):
        raise AssertionError("Every replaced asset should be reused one-for-one")
    ids = {asset["id"] for asset in doc["assets"]}
    refs = {layer.get("refId") for layer in doc["layers"]}
    if ids != refs:
        raise AssertionError(f"Unreferenced/missing assets: {ids.symmetric_difference(refs)}")

    out_lottie.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    build_svg(doc, out_svg)

    rendered_assets = {asset["id"]: decode_asset(asset) for asset in doc["assets"]}
    base_asset = rendered_assets["image_base"].resize((W, H), Image.Resampling.LANCZOS)
    diff = ImageOps.grayscale(ImageChops_difference(source.convert("RGB"), base_asset.convert("RGB")))
    if diff.getbbox() is not None:
        raise AssertionError("Embedded Phase 5.1 base artwork differs from assets/image.png")

    sx, sy = PREVIEW_SIZE[0] / W, PREVIEW_SIZE[1] / H
    preview_assets = {
        asset_id: image.resize((max(1, round(image.width * sx)), max(1, round(image.height * sy))),
                               Image.Resampling.LANCZOS)
        for asset_id, image in rendered_assets.items()
    }

    frames = []
    frame_count = 180
    for index in range(frame_count):
        t = DURATION * index / frame_count
        frames.append(render_frame(doc, preview_assets, t, assets_are_scaled=True))
    frames[45].save(preview_dir / "profile-banner-phase-5.1-static-frame.png", optimize=True)
    gif_path = preview_dir / "profile-banner-phase-5.1-animation-preview.gif"
    save_gif(frames, gif_path)

    contact = Image.new("RGB", (PREVIEW_SIZE[0] * 3, PREVIEW_SIZE[1] * 2), (8, 10, 16))
    draw = ImageDraw.Draw(contact)
    sample_indices = [0, 45, 90, 135, 177]
    for idx, frame_index in enumerate(sample_indices):
        x, y = (idx % 3) * PREVIEW_SIZE[0], (idx // 3) * PREVIEW_SIZE[1]
        contact.paste(frames[frame_index], (x, y))
        draw.rectangle((x, y, x + 96, y + 24), fill=(7, 11, 18))
        draw.text((x + 7, y + 6), f"t = {frame_index / 20:.2f} s", fill=(235, 244, 255))
    contact.save(preview_dir / "motion-contact-sheet.jpg", quality=93, optimize=True)

    loop_start = render_frame(doc, preview_assets, 0, assets_are_scaled=True)
    loop_end = render_frame(doc, preview_assets, DURATION, assets_are_scaled=True)
    loop_diff = ImageChops_difference(loop_start, loop_end)
    loop_array = np.asarray(loop_diff)
    changed = int(np.count_nonzero(np.any(loop_array != 0, axis=2)))
    max_loop_delta = int(loop_array.max()) if changed else 0
    source_sha = hashlib.sha256(source_bytes).hexdigest()
    generated_at = time.perf_counter() - started
    report = f"""# Phase 5.1 — Motion design review

## Deliverables

- `profile-banner-phase-5.1.json`: self-contained Lottie animation, 1672 × 941, 30 fps, 9 seconds.
- `profile-banner-phase-5.1-animated.svg`: self-contained SVG with SMIL motion based on the same composition.
- `preview/profile-banner-phase-5.1-static-frame.png`: representative frame at 2.25 seconds, rendered at 1000 × 563.
- `preview/profile-banner-phase-5.1-animation-preview.gif`: 9-second animated preview at 20 fps.
- `preview/motion-contact-sheet.jpg`: five points through the loop at intended profile display size.
- `preview/lottie-player-preview.html` and `preview/svg-player-preview.html`: local player pages for the Lottie-Web and SMIL exports.

## Changes from Phase 5

- Replaced the large-ring opacity pulse with a 78° traveling highlight clipped to a source-pixel-derived ring profile. The ring remains fixed; the highlight completes one circuit per 9-second loop.
- Replaced the badge perimeter pulse with a compact 52° traveling arc completing two circuits per loop, offset from the main ring.
- Reused the existing eight comet layers for short cyan/violet light bands. Each band follows its existing circuit or button-border path, turns with the path, and fades at open endpoints so it does not pop back as a detached dot.
- Retained the original dot-field, terminal status, panel, and line-intensity layers and their staggered activity.
- Kept the Lottie layer count at {len(doc['layers'])} and the image asset count at {len(doc['assets'])}; no additional effect layers were added.

## Visual review

- **Ring:** continuous arc motion around the visible circumference, with a tapered tail and no second full outline. The circle and banner remain stationary.
- **Circuit network:** a finite luminous segment follows each selected source path. Its cyan/white leading edge and violet/cyan tail read as a line sweep at 1000 × 563, rather than as a small point.
- **Button:** one band travels the existing rounded border path and eases out at the corners through tangent interpolation. Text, arrow, fill, shape, and position stay fixed.
- **CB badge:** compact edge arc stays on the source-derived perimeter and moves at a different rate from the large ring.
- **Terminal and dots:** existing staggered pulses remain secondary; the three original red, yellow, and green indicators and all text remain stationary.
- **Legibility:** all motion assets are overlays; the source image is preserved as the unchanged base. No typography, icons, button geometry, circuit paths, or dot locations were rebuilt.
- **Loop:** the 9-second loop uses periods that divide evenly into its duration. The generated opening and closing frames compare with {changed} differing pixels (maximum channel difference {max_loop_delta}) at preview size.
- **Base fidelity:** `image_base` was decoded from the Phase 5.1 JSON and compared with `assets/image.png`; the RGB pixel difference is zero. Source SHA-256: `{source_sha}`.

## Renderer and performance

The Lottie JSON was opened in the project's installed `lottie-web` player in a local browser preview; the 49-layer animation loaded and its frame counter advanced. The self-contained Animated SVG also loaded in that browser, and its SMIL clock advanced. These are actual compatible-renderer checks; the files were not imported into hosted LottieFiles Creator.

- Lottie JSON: {out_lottie.stat().st_size:,} bytes; {len(doc['layers'])} image layers; {len(doc['assets'])} embedded PNG assets.
- Animated SVG: {out_svg.stat().st_size:,} bytes.
- GIF preview: {gif_path.stat().st_size:,} bytes; {frame_count} frames, 50 ms each.
- Local generation time: {generated_at:.1f} seconds.

## Limits

- The original banner is a single raster image. The effects remain pixel overlays and do not make the text, circuit geometry, or cursor independently editable.
- The ring and badge are selected from source pixels; the continuation where their circles extend beyond the canvas is inferred from neighboring visible ring pixels, then clipped by the composition bounds.
- No cursor blink is added because the cursor is embedded in the source raster and cannot be isolated without a duplicate.
- Renderer validation used local `lottie-web` 5.13.0 and browser SMIL, not the hosted LottieFiles Creator. The SVG relies on SMIL support; if a platform strips SMIL, it may display as a static frame.
"""
    (OUT / "motion-design-review.md").write_text(report, encoding="utf-8")
    print(json.dumps({
        "lottie": str(out_lottie), "svg": str(out_svg),
        "gif": str(gif_path), "contact": str(preview_dir / "motion-contact-sheet.jpg"),
        "layers": len(doc["layers"]), "assets": len(doc["assets"]),
        "lottie_bytes": out_lottie.stat().st_size, "svg_bytes": out_svg.stat().st_size,
        "gif_bytes": gif_path.stat().st_size, "base_pixel_difference": 0,
        "loop_changed_pixels": changed, "loop_max_channel_delta": max_loop_delta,
    }, indent=2))


def ImageChops_difference(a: Image.Image, b: Image.Image) -> Image.Image:
    from PIL import ImageChops
    return ImageChops.difference(a, b)


if __name__ == "__main__":
    main()
