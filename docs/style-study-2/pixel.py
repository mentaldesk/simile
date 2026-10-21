"""Pixel art on one grid: the pieces snapped to `NATIVE` art pixels a metre in one limited palette,
frames drawn at play size snapped to that grid, and the residents drawn three ways.

`python pixel.py` pixelates out/pixel/smooth/, which `scenery.py pixel` builds, into
out/pixel/papercraft/.
"""

import json
import math
import shutil

import numpy as np
from common import OUT
from PIL import Image

NATIVE = 20
"""Art pixels a metre: a tile is 22 and a resident about 41."""
PPM = 120
BLOCK = PPM // NATIVE
"""Pieces are stored at #309's 120 px/m, so each art pixel is this many pixels across."""
COLOURS = 64
"""The scenery's palette."""
SHADES = (0.72, 0.86, 1.0, 1.12)
"""Each resident colour's ramp, as a pixel artist would shade it."""
SMOOTH = OUT / "pixel" / "smooth"
SNAPPED = OUT / "pixel" / "papercraft"


def premultiplied_resize(image: Image.Image, size: tuple[int, int]) -> np.ndarray:
    """`image` area-averaged to `size`, with its colours weighted by alpha so the backdrop
    doesn't bleed in."""
    a = np.asarray(image.convert("RGBA"), dtype=np.float32) / 255
    a[..., :3] *= a[..., 3:]
    channels = [
        np.asarray(Image.fromarray(a[..., i]).resize(size, Image.BOX), dtype=np.float32)
        for i in range(4)
    ]
    out = np.stack(channels, axis=2)
    out[..., :3] /= np.maximum(out[..., 3:], 1e-6)
    return np.clip(out, 0, 1) * 255


def palette_image(colours: np.ndarray) -> Image.Image:
    p = Image.new("P", (1, 1))
    flat = [int(v) for v in np.asarray(colours, dtype=np.uint8).ravel()]
    p.putpalette(flat + flat[:3] * (256 - len(colours)))
    return p


def quantise(rgb: np.ndarray, palette: Image.Image) -> np.ndarray:
    """Each pixel's nearest palette colour, with no dithering."""
    image = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB")
    return np.asarray(image.quantize(palette=palette, dither=Image.Dither.NONE).convert("RGB"))


def pixelate(image: Image.Image, palette: Image.Image, scale: int = BLOCK) -> Image.Image:
    """`image` as art pixels `scale` px across: area-averaged, its alpha made hard, its colours
    from `palette`, and scaled back up with nearest-neighbour."""
    native = (max(1, round(image.width / scale)), max(1, round(image.height / scale)))
    a = premultiplied_resize(image, native)
    rgb = quantise(a[..., :3], palette)
    alpha = np.where(a[..., 3] >= 128, 255, 0).astype(np.uint8)
    small = Image.fromarray(np.dstack([rgb, alpha]), "RGBA")
    return small.resize((native[0] * scale, native[1] * scale), Image.NEAREST)


def scenery_palette(folder=SMOOTH, colours: int = COLOURS, apart: float = 8.0) -> np.ndarray:
    """One palette for every piece: a median cut over all their opaque pixels, each piece
    weighted alike, then the most used colours kept that are at least `apart` (CIE76) from each
    other. So a wall gets one or two shades rather than a band of near-twins, and rarer hues like
    magenta flowers keep a place."""
    from simile.dolls.colour import cielab

    manifest = json.loads((folder / "manifest.json").read_text())
    samples = []
    rng = np.random.default_rng(0)
    for entry in manifest["pieces"].values():
        a = np.asarray(Image.open(folder / entry["file"]).convert("RGBA"))
        rgb = a[..., :3][a[..., 3] > 128]
        if len(rgb):
            samples.append(rgb[rng.integers(0, len(rgb), 4000)])
    pool = np.concatenate(samples)[None]
    many = 3 * colours
    q = Image.fromarray(pool.astype(np.uint8)).quantize(many, Image.Quantize.MEDIANCUT)
    candidates = np.asarray(q.getpalette()[: 3 * many]).reshape(-1, 3)
    counts = np.bincount(np.asarray(q).ravel(), minlength=many)[:many]
    lab = cielab(candidates.astype(np.float64))
    kept: list[int] = []
    for i in np.argsort(-counts):
        if counts[i] and all(np.linalg.norm(lab[i] - lab[j]) >= apart for j in kept):
            kept.append(int(i))
        if len(kept) == colours:
            break
    return candidates[kept]


def snap_pieces(source=SMOOTH, target=SNAPPED) -> np.ndarray:
    """Every piece pixelated onto the grid in the scenery palette, and the manifest with their
    new sizes. Returns the palette."""
    colours = scenery_palette(source)
    palette = palette_image(colours)
    manifest = json.loads((source / "manifest.json").read_text())
    if target.exists():
        shutil.rmtree(target)
    for entry in manifest["pieces"].values():
        image = Image.open(source / entry["file"]).convert("RGBA")
        snapped = pixelate(image, palette)
        if entry["kind"] in ("paper", "ground", "layer", "strip"):
            snapped = snapped.convert("RGB") if entry["kind"] == "paper" else snapped
        path = target / entry["file"]
        path.parent.mkdir(parents=True, exist_ok=True)
        snapped.save(path, "WEBP", lossless=True)
        if entry["kind"] in ("front", "glow"):
            entry["height"] = round(snapped.height / PPM, 3)
        entry["size"] = list(snapped.size)
    (target / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    (target / "palette.json").write_text(json.dumps(colours.tolist()))
    return colours


def palette() -> Image.Image:
    return palette_image(np.asarray(json.loads((SNAPPED / "palette.json").read_text())))


def mode_blocks(index: np.ndarray, k: int) -> np.ndarray:
    """Each k x k block's most common value: ties go to the first in reading order."""
    h, w = index.shape[0] // k, index.shape[1] // k
    blocks = index[: h * k, : w * k].reshape(h, k, w, k).transpose(0, 2, 1, 3).reshape(h, w, -1)
    counts = (blocks[..., :, None] == blocks[..., None, :]).sum(axis=3)
    return np.take_along_axis(blocks, counts.argmax(axis=2)[..., None], axis=2)[..., 0]


def snap_frame(frame: Image.Image, k: int, colours: Image.Image | None = None) -> Image.Image:
    """A frame drawn at k times the art's pixels, snapped to its grid: each pixel its nearest
    palette colour, then each k x k block its most common colour. Returns the native frame."""
    p = colours or palette()
    q = np.asarray(frame.convert("RGB").quantize(palette=p, dither=Image.Dither.NONE))
    index = mode_blocks(q.astype(np.int32), k)
    lut = np.asarray(p.getpalette()[: 3 * 256], dtype=np.uint8).reshape(-1, 3)
    return Image.fromarray(lut[index], "RGB")


def up(image: Image.Image, k: int) -> Image.Image:
    return image.resize((image.width * k, image.height * k), Image.NEAREST)


# The residents: the rig drawn at the art's own size, or drawn smooth and each frame pixelated.


def doll_palette(doll, shades=SHADES) -> Image.Image:
    """A resident's palette: each flat colour of their pieces in a few shades, and the ink."""
    from simile.dolls.sheet import regions

    colours = []
    for spec in doll.pieces.values():
        x, y, w, h = spec["frame"]
        _, main, _ = regions(doll.flat.crop((x, y, x + w, y + h)))
        colours += [c for c in main]
    base = np.unique(np.round(np.asarray(colours)), axis=0)
    ramp = [np.clip(base * s, 0, 255) for s in shades]
    ramp.append(np.array([[34, 26, 30]]))
    pool = np.unique(np.concatenate(ramp).round(), axis=0)[:256]
    return palette_image(pool)


def region_ids(flat: Image.Image, size: tuple[int, int]):
    """For a flat doll piece shrunk to `size` art pixels, the colour region covering most of each
    one (-1 where it's mostly clear), the region colours, and each art pixel's block."""
    from simile.dolls.sheet import regions

    nearest, main, opaque = regions(flat)
    xs = np.linspace(0, flat.width, size[0] + 1).round().astype(int)
    ys = np.linspace(0, flat.height, size[1] + 1).round().astype(int)
    ids = np.full((size[1], size[0]), -1)
    blocks = {}
    for j in range(size[1]):
        for i in range(size[0]):
            block = (slice(ys[j], ys[j + 1]), slice(xs[i], xs[i + 1]))
            inside = opaque[block]
            if inside.size == 0 or inside.mean() < 0.5:
                continue
            ids[j, i] = np.bincount(nearest[block][inside], minlength=len(main)).argmax()
            blocks[j, i] = block, inside & (nearest[block] == ids[j, i])
    return ids, main, blocks


def region_pixels(painted: Image.Image, flat: Image.Image, size: tuple[int, int]) -> Image.Image:
    """A doll piece as `size` art pixels: each one takes the flat colour region that covers most
    of it, and the shade of that colour's ramp nearest the painting's light there, relative to
    the region's usual light, as #310's restore pins a region's median. So every art pixel is one
    of its region's own shades, and most are its flat colour."""
    ids, main, blocks = region_ids(flat, size)
    p = np.asarray(painted.convert("RGBA"), dtype=np.float64)
    lum = p[..., :3] @ np.array([0.299, 0.587, 0.114])
    light = np.ones(ids.shape)
    for (j, i), (block, mine) in blocks.items():
        light[j, i] = np.median(lum[block][mine])
    out = np.zeros((size[1], size[0], 4), dtype=np.uint8)
    for region in np.unique(ids[ids >= 0]):
        here = ids == region
        usual = max(float(np.median(light[here])), 1.0)
        for j, i in zip(*np.nonzero(here), strict=True):
            shade = min(SHADES, key=lambda s: abs(s - light[j, i] / usual))
            out[j, i, :3] = np.clip(main[region] * shade, 0, 255)
            out[j, i, 3] = 255
    return Image.fromarray(out, "RGBA")


def rotate_nearest(image: Image.Image, angle: float, pivot, smooth: bool) -> tuple:
    """`image` turned `angle` degrees clockwise about `pivot` with nearest-neighbour, or, if
    `smooth`, at eight times its size first and back down by each block's most common colour,
    as pixel artists' rotation tools do. Returns the turned image and where the pivot went."""
    corners = [(0, 0), (image.width, 0), (0, image.height), (image.width, image.height)]
    r = math.ceil(max(math.hypot(x - pivot[0], y - pivot[1]) for x, y in corners)) + 2
    square = Image.new("RGBA", (2 * r, 2 * r), (0, 0, 0, 0))
    square.paste(image, (round(r - pivot[0]), round(r - pivot[1])))
    if not smooth:
        return square.rotate(-angle, resample=Image.NEAREST, center=(r, r)), (r, r)
    k = 8
    big = up(square, k).rotate(-angle, resample=Image.NEAREST, center=(r * k, r * k))
    a = np.asarray(big)
    keys = (a[..., 0].astype(np.int64) << 24) | (a[..., 1].astype(np.int64) << 16)
    keys |= (a[..., 2].astype(np.int64) << 8) | a[..., 3].astype(np.int64)
    picked = mode_blocks(keys, k)
    rgba = np.stack([(picked >> s) & 255 for s in (24, 16, 8, 0)], axis=2).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA"), (r, r)


if __name__ == "__main__":
    snap_pieces()
