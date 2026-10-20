"""Alpha cut-outs for pictures painted on a plain white background."""

import hashlib
import urllib.request
from functools import cache

import numpy as np
from common import OUT
from PIL import Image, ImageFilter

MODEL = OUT / "models" / "isnet-general-use.onnx"
MODEL_URL = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/isnet-general-use.onnx"
MODEL_MD5 = "fc16ebd8b0c10d971d3513d564d01e29"


@cache
def session():
    import onnxruntime as ort

    if not MODEL.exists():
        MODEL.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(MODEL_URL, MODEL)
    if hashlib.md5(MODEL.read_bytes()).hexdigest() != MODEL_MD5:
        raise RuntimeError(f"{MODEL} doesn't match the published checksum")
    return ort.InferenceSession(str(MODEL), providers=["CPUExecutionProvider"])


def segment(image: Image.Image) -> Image.Image:
    """IS-Net's foreground mask, as rembg's `isnet-general-use` session prepares it."""
    small = np.asarray(image.convert("RGB").resize((1024, 1024), Image.Resampling.LANCZOS))
    x = small / max(small.max(), 1e-6) - np.array([0.485, 0.456, 0.406])
    x = x.transpose(2, 0, 1)[None].astype(np.float32)
    s = session()
    pred = s.run(None, {s.get_inputs()[0].name: x})[0][0, 0]
    pred = (pred - pred.min()) / max(pred.max() - pred.min(), 1e-6)
    mask = Image.fromarray((pred * 255).astype(np.uint8))
    return mask.resize(image.size, Image.Resampling.LANCZOS)


def background(image: Image.Image) -> np.ndarray:
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


def unmix(image: Image.Image, mask: Image.Image) -> Image.Image:
    """RGBA with the white background taken back out of the semi-transparent edge pixels."""
    a = np.asarray(image.convert("RGB"), dtype=np.float32)
    m = np.asarray(mask, dtype=np.float32)[..., None] / 255
    bg = background(image)
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
    pale parts like a cream awning stripe, and the key alone keeps the baked shadows."""
    seg = np.asarray(clean(segment(image)), dtype=np.float32)
    keyed = np.asarray(key(image), dtype=np.float32) * ~shadowish(image)
    a = np.asarray(image.convert("RGB"), dtype=np.float32)
    enclosed_gap = (np.abs(a - background(image)).max(axis=2) < 10) & (seg < 80)
    keyed[enclosed_gap] = 0
    return fill_holes(clean(Image.fromarray(np.maximum(seg, keyed).astype(np.uint8)), floor=8))


def fill_holes(mask: Image.Image, largest: int = 600) -> Image.Image:
    """The mask with small enclosed gaps made solid, leaving big ones like a ladder's rungs."""
    import cv2

    m = np.asarray(mask).copy()
    gaps = (m < 128).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(gaps, connectivity=4)
    edge = set(np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]])))
    for i in range(1, count):
        if i not in edge and stats[i, cv2.CC_STAT_AREA] <= largest:
            m[labels == i] = 255
    return Image.fromarray(m)


def skyline(mask: Image.Image) -> Image.Image:
    """A layer's mask made solid from its top edge down, so pale paper isn't see-through."""
    m = np.asarray(mask, dtype=np.float32) / 255
    solid = m > 0.5
    rows = np.arange(m.shape[0])[:, None]
    top = np.where(solid.any(axis=0), solid.argmax(axis=0), m.shape[0])
    bottom = np.where(solid.any(axis=0), m.shape[0] - 1 - solid[::-1].argmax(axis=0), -1)
    inside = (rows >= top) & (rows <= bottom)
    return Image.fromarray((np.where(inside, 1.0, m) * 255).astype(np.uint8))


def cut(image: Image.Image, method: str = "hybrid", trim: bool = True) -> Image.Image:
    masks = {"isnet": lambda i: clean(segment(i)), "key": lambda i: clean(key(i)), "hybrid": hybrid}
    sprite = unmix(image, masks[method](image))
    if trim and (box := sprite.getchannel("A").getbbox()):
        sprite = sprite.crop(box)
    return sprite


def baked_shadow(image: Image.Image, sprite_mask: Image.Image) -> Image.Image:
    """The shadow the painting has on the background around the object, as black with alpha."""
    a = np.asarray(image.convert("RGB"), dtype=np.float32)
    bg = background(image)
    lum = a.mean(axis=2) / bg.mean()
    chroma = a.max(axis=2) - a.min(axis=2)
    dark = np.clip(1 - lum, 0, 1) * (chroma < 24)
    m = np.asarray(sprite_mask, dtype=np.float32) / 255
    alpha = dark * (1 - m)
    out = np.zeros((*alpha.shape, 4), dtype=np.uint8)
    out[..., 3] = np.clip(alpha * 255 * 1.6, 0, 255).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def drop_shadow(
    sprite: Image.Image, offset: tuple[int, int], blur: float, opacity: float, pad: int = 0
) -> tuple[Image.Image, tuple[int, int]]:
    """A shadow made from the sprite's alpha, and where its top-left sits relative to the
    sprite's."""
    pad = pad or round(blur * 3) + max(abs(offset[0]), abs(offset[1]))
    w, h = sprite.size
    shadow = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    alpha = Image.new("L", shadow.size, 0)
    alpha.paste(sprite.getchannel("A").point(lambda v: round(v * opacity)), (pad, pad))
    shadow.putalpha(alpha.filter(ImageFilter.GaussianBlur(blur)))
    return shadow, (offset[0] - pad, offset[1] - pad)
