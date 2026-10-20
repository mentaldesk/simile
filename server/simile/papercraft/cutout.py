"""Alpha cut-outs for pictures painted on a plain background: IS-Net's mask plus a colour key.

onnxruntime and OpenCV are imported only when used. OpenCV comes with the `images` extra.
"""

import hashlib
import os
import urllib.request
from functools import cache
from pathlib import Path

import numpy as np
from PIL import Image

MODEL_URL = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/isnet-general-use.onnx"
MODEL_MD5 = "fc16ebd8b0c10d971d3513d564d01e29"


def cache_dir() -> Path:
    return Path(os.environ.get("XDG_CACHE_HOME", "~/.cache")).expanduser() / "simile"


def model_path() -> Path:
    return cache_dir() / "models" / "isnet-general-use.onnx"


def ensure_model() -> Path:
    """IS-Net's weights (179 MB, rembg's release), downloaded into the cache the first time and
    checked against their MD5."""
    path = model_path()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_suffix(".part")
        urllib.request.urlretrieve(MODEL_URL, partial)
        partial.rename(path)
    if hashlib.md5(path.read_bytes()).hexdigest() != MODEL_MD5:
        raise RuntimeError(f"{path} doesn't match IS-Net's published checksum; delete it")
    return path


@cache
def _session():
    import onnxruntime as ort

    return ort.InferenceSession(str(ensure_model()), providers=["CPUExecutionProvider"])


def segment(image: Image.Image) -> Image.Image:
    """IS-Net's foreground mask, prepared as rembg's `isnet-general-use` session does."""
    small = np.asarray(image.convert("RGB").resize((1024, 1024), Image.Resampling.LANCZOS))
    x = small / max(small.max(), 1e-6) - np.array([0.485, 0.456, 0.406])
    x = x.transpose(2, 0, 1)[None].astype(np.float32)
    session = _session()
    pred = session.run(None, {session.get_inputs()[0].name: x})[0][0, 0]
    pred = (pred - pred.min()) / max(pred.max() - pred.min(), 1e-6)
    mask = Image.fromarray((pred * 255).astype(np.uint8))
    return mask.resize(image.size, Image.Resampling.LANCZOS)


def background(image: Image.Image) -> np.ndarray:
    """The backdrop's colour: the median of the border pixels."""
    a = np.asarray(image.convert("RGB"), dtype=np.float32)
    border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    return np.median(border, axis=0)


def key(image: Image.Image, lo: float = 10, hi: float = 34) -> Image.Image:
    """A colour key: the background is whatever near-background colour touches the border."""
    import cv2

    a = np.asarray(image.convert("RGB"), dtype=np.float32)
    d = np.abs(a - background(image)).max(axis=2)
    near = (d < hi).astype(np.uint8)
    _, labels = cv2.connectedComponents(near, connectivity=4)
    edge = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
    outside = np.isin(labels, edge[edge > 0]) & (near > 0)
    alpha = np.where(outside, np.clip((d - lo) / (hi - lo), 0, 1), 1.0)
    return Image.fromarray((alpha * 255).astype(np.uint8))


def clean(mask: Image.Image, floor: int = 24, islands: int = 400) -> Image.Image:
    """The mask with faint haze cut off and stray specks removed."""
    import cv2

    m = np.asarray(mask, dtype=np.float32)
    m = np.clip((m - floor) / (255 - 2 * floor), 0, 1)
    solid = (m > 0.5).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(solid, connectivity=8)
    keep = np.zeros(count, dtype=bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= islands
    near_kept = cv2.dilate(keep[labels].astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    m = np.where(near_kept, m, 0)
    return Image.fromarray((m * 255).astype(np.uint8))


def unmix(image: Image.Image, mask: Image.Image, bg: np.ndarray | None = None) -> Image.Image:
    """RGBA with the background colour taken back out of the semi-transparent edge pixels."""
    a = np.asarray(image.convert("RGB"), dtype=np.float32)
    m = np.asarray(mask, dtype=np.float32)[..., None] / 255
    bg = background(image) if bg is None else bg
    fg = np.where(m > 0.05, (a - (1 - m) * bg) / np.maximum(m, 0.05), a)
    rgba = np.concatenate([np.clip(fg, 0, 255), m * 255], axis=2).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


def shadowish(image: Image.Image) -> np.ndarray:
    """Pixels that look like a soft shadow on the background: darker, but the same hue."""
    a = np.asarray(image.convert("RGB"), dtype=np.float32)
    ratio = a / np.maximum(background(image), 1)
    level = ratio.mean(axis=2)
    return (ratio.max(axis=2) - ratio.min(axis=2) < 0.07) & (level > 0.4) & (level < 0.985)


def hybrid(image: Image.Image) -> Image.Image:
    """IS-Net's mask, plus whatever the colour key keeps that isn't shadow: IS-Net alone drops
    pale parts like a cream awning stripe, and the key alone keeps the painted shadows."""
    seg = np.asarray(clean(segment(image)), dtype=np.float32)
    keyed = np.asarray(key(image), dtype=np.float32) * ~shadowish(image)
    a = np.asarray(image.convert("RGB"), dtype=np.float32)
    enclosed_gap = (np.abs(a - background(image)).max(axis=2) < 10) & (seg < 80)
    keyed[enclosed_gap] = 0
    return fill_holes(clean(Image.fromarray(np.maximum(seg, keyed).astype(np.uint8)), floor=8))


SHADOWS = {"shadows": (0.16, 0.3), "tinted shadows": (0.3, 0.3), "deep shadows": (0.16, 0.05)}
"""Kinds of painted shadow to cut away: how saturated it may be, and how dark, against the
backdrop. A shadow tinted by a bright object is more saturated, and a deep one darker, which
only does for an object with no near-black parts."""


def shadows(image: Image.Image, kind: str = "shadows") -> np.ndarray:
    """Shadow painted on the backdrop: darker than it and nearly grey."""
    greyness, darkest = SHADOWS[kind]
    a = np.asarray(image.convert("RGB"), dtype=np.float32)
    top, bottom = a.max(axis=2), a.min(axis=2)
    saturation = (top - bottom) / np.maximum(top, 1)
    level = top / max(background(image).max(), 1)
    return (saturation < greyness) & (level > darkest) & (level < 0.99)


def tidy(image: Image.Image, mask: Image.Image, cut: tuple[str, ...]) -> Image.Image:
    """`mask` with what `cut` names cut away: a kind of painted shadow from `SHADOWS`, and
    `gaps`, the backdrop showing through the object, between a chair's legs or inside a wheel.
    Specks much smaller than the object go too."""
    m = np.asarray(mask, dtype=np.float32).copy()
    for kind in set(cut) & set(SHADOWS):
        m[shadows(image, kind)] = 0
    gaps = "gaps" in cut
    if gaps:
        a = np.asarray(image.convert("RGB"), dtype=np.float32)
        m[np.abs(a - background(image)).max(axis=2) < 10] = 0
    return _drop_specks(clean(Image.fromarray(m.astype(np.uint8)), floor=8))


def _drop_specks(mask: Image.Image, smallest: float = 0.03) -> Image.Image:
    import cv2

    m = np.asarray(mask).copy()
    count, labels, stats, _ = cv2.connectedComponentsWithStats((m > 128).astype(np.uint8), 8)
    if count > 2:
        areas = stats[1:, cv2.CC_STAT_AREA]
        small = 1 + np.flatnonzero(areas < smallest * areas.max())
        near = cv2.dilate(np.isin(labels, small).astype(np.uint8), np.ones((5, 5), np.uint8))
        m[near > 0] = 0
    return Image.fromarray(m)


def fill_holes(mask: Image.Image, largest: int = 600) -> Image.Image:
    """The mask with small enclosed gaps made solid, leaving big ones like a ladder's rungs."""
    import cv2

    m = np.asarray(mask).copy()
    gaps = (m < 128).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(gaps, connectivity=4)
    edge = set(np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]])))
    small = [i for i in range(1, count) if i not in edge and stats[i, cv2.CC_STAT_AREA] <= largest]
    m[np.isin(labels, small)] = 255
    return Image.fromarray(m)


def skyline(mask: Image.Image) -> Image.Image:
    """A layer's mask made solid between its top and bottom edges in every column, so pale paper
    isn't see-through."""
    m = np.asarray(mask, dtype=np.float32) / 255
    solid = m > 0.5
    rows = np.arange(m.shape[0])[:, None]
    top = np.where(solid.any(axis=0), solid.argmax(axis=0), m.shape[0])
    bottom = np.where(solid.any(axis=0), m.shape[0] - 1 - solid[::-1].argmax(axis=0), -1)
    inside = (rows >= top) & (rows <= bottom)
    return Image.fromarray((np.where(inside, 1.0, m) * 255).astype(np.uint8))
