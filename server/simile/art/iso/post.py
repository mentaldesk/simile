"""What happens to a render after Blender: glow, ground chunks, and the runtime light map."""

import math

import numpy as np
from PIL import Image, ImageFilter

CHUNK_PX = 2048
OPEN_PERCENTILE = 99
FEET_RADIUS = 0.35


def glow(image: Image.Image, radius: int, strength: float) -> Image.Image:
    """A halo around bright, saturated pixels (neon, lamps, screens), inside the image's alpha."""
    if strength <= 0:
        return image
    a = np.asarray(image.convert("RGB")).astype(np.float32) / 255
    hi, lo = a.max(axis=2), a.min(axis=2)
    sat = (hi - lo) / np.maximum(hi, 1e-3)
    mask = np.clip((hi - 0.72) / 0.25, 0, 1) * np.clip((sat - 0.35) / 0.35, 0, 1)
    bright = Image.fromarray((a * mask[..., None] * 255).astype(np.uint8))
    halo = np.asarray(bright.filter(ImageFilter.GaussianBlur(radius))).astype(np.float32) / 255
    out = 1 - (1 - a) * (1 - np.clip(halo * strength * 1.6, 0, 1))
    rgb = np.round(out * 255).astype(np.uint8)
    if image.mode != "RGBA":
        return Image.fromarray(rgb)
    alpha = np.asarray(image.getchannel("A"))
    rgb[alpha == 0] = 0
    return Image.fromarray(np.dstack([rgb, alpha]), "RGBA")


def chunks(
    width: int, height: int, size: int = CHUNK_PX
) -> list[tuple[int, int, int, int, int, int]]:
    """A grid of even pieces no bigger than size: (column, row, x, y, width, height)."""
    cols, rows = math.ceil(width / size), math.ceil(height / size)
    xs = [round(width * i / cols) for i in range(cols + 1)]
    ys = [round(height * j / rows) for j in range(rows + 1)]
    return [
        (i, j, xs[i], ys[j], xs[i + 1] - xs[i], ys[j + 1] - ys[j])
        for j in range(rows)
        for i in range(cols)
    ]


def _luma(rgb: np.ndarray) -> np.ndarray:
    return rgb @ np.array([0.2126, 0.7152, 0.0722], np.float32)


def _disc_mean(a: np.ndarray, radius: float) -> np.ndarray:
    r = math.floor(radius)
    offsets = [
        (i, j) for i in range(-r, r + 1) for j in range(-r, r + 1) if i * i + j * j <= radius**2
    ]
    pad = ((r, r), (r, r)) + ((0, 0),) * (a.ndim - 2)
    padded = np.pad(a, pad, mode="edge")
    h, w = a.shape[:2]
    total = sum(padded[r + j : r + j + h, r + i : r + i + w] for i, j in offsets)
    return total / len(offsets)


def light_map(
    sunsky: np.ndarray, sun: np.ndarray, lights: np.ndarray, elevation: float, px_per_tile: int
) -> tuple[Image.Image, float]:
    """A resident's light at their feet, relative to the open square, and its RGB scale."""
    sky = np.maximum(sunsky - sun, 0)
    e = math.radians(elevation)
    upright = math.cos(e) / (math.pi * math.sin(e))
    figure = sun * upright + 0.5 * (sky + lights)
    level = _luma(sunsky)
    open_ground = level >= np.percentile(level, OPEN_PERCENTILE)
    open_sun = sun[open_ground].mean(axis=0)
    open_light = open_sun * upright + 0.5 * sky[open_ground].mean(axis=0)
    radius = FEET_RADIUS * px_per_tile
    ratio = _disc_mean(figure, radius) / np.maximum(open_light, 1e-6)
    tint = np.power(np.maximum(ratio, 0), 1 / 2.2)
    in_sun = np.clip(_luma(_disc_mean(sun, radius)) / max(float(_luma(open_sun)), 1e-6), 0, 1)
    scale = max(round(float(tint.max()), 3), 1.0)
    rgba = np.dstack([np.clip(tint / scale, 0, 1), in_sun])
    return Image.fromarray(np.round(rgba * 255).astype(np.uint8), "RGBA"), scale
