"""Laying a doll's flat pieces out on a sheet for the painter, and cutting the painted sheet back
into pieces: each along its known outline, its colours pulled back to the flat ones, and its paper
texture made strong enough to read at street size."""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageFilter

from simile.dolls.colour import delta_e
from simile.dolls.look import Look
from simile.dolls.pieces import Piece, flat_pieces

SIZE = (1024, 768)
MOST = 8.0
"""Pixels per unit on a sheet, when the pieces fit."""
GAP = 40
BACKGROUND = (214, 210, 202)
KEEP_COLOUR = 0.9
TEXTURE = 1.8
"""How much the painting's mottling, at the scale that survives street size, is strengthened."""
LAYOUTS: dict[str, tuple[tuple[str, ...], ...]] = {
    "side": (
        ("head", "shoe"),
        ("torso",),
        ("upper_leg",),
        ("lower_leg",),
        ("upper_arm",),
        ("lower_arm",),
    ),
    "front_back": (("head_front", "shoe_front"), ("torso_front",), ("torso_back",), ("head_back",)),
}
"""Each sheet's columns, left to right, each stacked top to bottom. The prompts describe them."""


@dataclass
class Sheet:
    name: str
    scale: float
    pieces: dict[str, Piece]
    spots: dict[str, tuple[int, int]]

    def image(self) -> Image.Image:
        out = Image.new("RGB", SIZE, BACKGROUND)
        for name, (x, y) in self.spots.items():
            out.paste(self.pieces[name].image, (x, y), self.pieces[name].image)
        return out

    def crop(self, painted: Image.Image, name: str) -> Image.Image:
        x, y = self.spots[name]
        w, h = self.pieces[name].image.size
        return painted.convert("RGB").crop((x, y, x + w, y + h))


def names(layout: str) -> tuple[str, ...]:
    return tuple(name for column in LAYOUTS[layout] for name in column)


def fits(pieces: dict[str, Piece], columns: tuple[tuple[str, ...], ...]) -> bool:
    width = sum(max(pieces[n].image.width for n in c) for c in columns)
    height = max(sum(pieces[n].image.height for n in c) + GAP * (len(c) + 1) for c in columns)
    return width + GAP * (len(columns) + 1) <= SIZE[0] and height <= SIZE[1]


def sheet(name: str, look: Look) -> Sheet:
    """The pieces in their columns at the largest scale up to `MOST` that fits, centred."""
    columns = LAYOUTS[name]
    scale = MOST
    while not fits(pieces := flat_pieces(look, scale, names(name)), columns):
        scale -= 0.25
    widths = [max(pieces[n].image.width for n in c) for c in columns]
    x = (SIZE[0] - sum(widths) - GAP * (len(columns) - 1)) // 2
    spots: dict[str, tuple[int, int]] = {}
    for column, w in zip(columns, widths, strict=True):
        height = sum(pieces[n].image.height for n in column) + GAP * (len(column) - 1)
        y = (SIZE[1] - height) // 2
        for n in column:
            spots[n] = (x + (w - pieces[n].image.width) // 2, y)
            y += pieces[n].image.height + GAP
        x += w + GAP
    return Sheet(name, scale, pieces, spots)


def regions(flat: Image.Image) -> tuple[NDArray[np.intp], NDArray[np.float64], NDArray[np.bool_]]:
    """Each opaque pixel's flat-colour region: the colours the piece was drawn in, found where a
    pixel matches its four neighbours, and which one each pixel is nearest, so antialiased edges
    join a neighbour."""
    f = np.asarray(flat.convert("RGBA"), dtype=np.float64)
    opaque = f[..., 3] > 0
    solid = f[..., 3] == 255
    same = solid.copy()
    for shift, axis in ((1, 0), (-1, 0), (1, 1), (-1, 1)):
        same &= (np.roll(f, shift, axis=axis) == f).all(axis=2)
    colours, counts = np.unique(f[same][:, :3], axis=0, return_counts=True)
    main = colours[counts >= 8]
    nearest = np.argmin(((f[..., None, :3] - main[None, None]) ** 2).sum(axis=3), axis=2)
    return nearest, main, opaque


def restore(painted: Image.Image, flat: Image.Image, amount: float = KEEP_COLOUR) -> Image.Image:
    """Scales each region of `painted` so its mean moves `amount` of the way to the region's
    flat colour, keeping the painted texture and shading."""
    p = np.asarray(painted.convert("RGB"), dtype=np.float64)
    nearest, main, opaque = regions(flat)
    f = np.asarray(flat.convert("RGB"), dtype=np.float64)
    out = p.copy()
    for i, target in enumerate(main):
        region = opaque & (nearest == i)
        core = region & (np.abs(f - target).max(axis=2) < 1)
        if not core.any():
            continue
        mean = p[core].mean(axis=0)
        gain = np.clip(np.maximum(target, 8) / np.maximum(mean, 8), 0.15, 4.0)
        out[region] = p[region] * (1 + (gain - 1) * amount)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


def _box(a: NDArray[np.float64], r: int, axis: int) -> NDArray[np.float64]:
    pad = [(0, 0)] * a.ndim
    pad[axis] = (r + 1, r)
    c = np.cumsum(np.pad(a, pad, mode="edge"), axis=axis)
    n = a.shape[axis]
    upper = np.take(c, range(2 * r + 1, 2 * r + 1 + n), axis=axis)
    lower = np.take(c, range(n), axis=axis)
    return (upper - lower) / (2 * r + 1)


def gaussian(a: NDArray[np.float64], sigma: float) -> NDArray[np.float64]:
    """About a Gaussian blur over the first two axes, as three box blurs, with edges extended."""
    r = max(1, round((np.sqrt(4 * sigma**2 + 1) - 1) / 2))
    for _ in range(3):
        a = _box(_box(a, r, 0), r, 1)
    return a


def _blur(values: NDArray[np.float64], mask: NDArray[np.float64], sigma: float) -> NDArray:
    """A blur inside `mask` only, so neighbouring regions don't bleed into each other."""
    both = gaussian(np.concatenate([values * mask[..., None], mask[..., None]], axis=2), sigma)
    return both[..., :-1] / np.maximum(both[..., -1:], 1e-6)


def strengthen(
    painted: Image.Image, flat: Image.Image, scale: float, gain: float = TEXTURE
) -> Image.Image:
    """Boosts the painting's texture between about a third and two units across, the band that
    survives at street size, region by region so no edge gets a halo. `scale` is pixels a unit."""
    p = np.asarray(painted.convert("RGB"), dtype=np.float64)
    nearest, main, opaque = regions(flat)
    out = p.copy()
    fine, coarse = 0.3 * scale, 2.0 * scale
    margin = int(3 * coarse) + 1
    for i in range(len(main)):
        region = opaque & (nearest == i)
        if region.sum() < 30:
            continue
        ys, xs = np.nonzero(region)
        y0, y1 = max(0, ys.min() - margin), min(p.shape[0], ys.max() + margin + 1)
        x0, x1 = max(0, xs.min() - margin), min(p.shape[1], xs.max() + margin + 1)
        crop, mask = p[y0:y1, x0:x1], region[y0:y1, x0:x1].astype(np.float64)
        band = _blur(crop, mask, fine) - _blur(crop, mask, coarse)
        inside = region[y0:y1, x0:x1]
        out[y0:y1, x0:x1][inside] = crop[inside] + band[inside] * (gain - 1)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


def cut(sheet: Sheet, painted: Image.Image) -> dict[str, Image.Image]:
    """Each painted piece as RGB, cropped to its flat piece, restored to its colours and
    strengthened. Outside its outline it's filled from its edge, so scaling it doesn't bleed
    the sheet's background in."""
    out = {}
    for name, flat in sheet.pieces.items():
        crop = restore(sheet.crop(painted, name), flat.image)
        crop = strengthen(crop, flat.image, sheet.scale)
        out[name] = bleed(crop, flat.image.getchannel("A"))
    return out


def bleed(image: Image.Image, alpha: Image.Image) -> Image.Image:
    """`image` with everything outside `alpha` replaced by the nearby colours inside it."""
    rgb = np.asarray(image.convert("RGB"), dtype=np.float64)
    inside = np.asarray(alpha.filter(ImageFilter.MinFilter(3)), dtype=np.float64) / 255
    inside = (inside > 0.99).astype(np.float64)
    out = rgb * inside[..., None]
    filled = inside.copy()
    for sigma in (1.0, 2.0, 4.0, 8.0):
        spread = _blur(rgb, inside, sigma)
        reach = gaussian(inside[..., None], sigma)[..., 0] > 1e-3
        todo = (filled == 0) & reach
        out[todo] = spread[todo]
        filled[todo] = 1
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


def misplaced(sheet: Sheet, painted: Image.Image) -> dict[str, float]:
    """For each piece, the share of its inside the painting left as bare background: high when
    the painter moved or dropped a piece."""
    out = {}
    for name, flat in sheet.pieces.items():
        crop = np.asarray(sheet.crop(painted, name), dtype=np.float64)
        f = np.asarray(flat.image, dtype=np.float64)
        alpha = np.asarray(flat.image.getchannel("A").filter(ImageFilter.MinFilter(5))) > 250
        unlike = delta_e(f[..., :3], BACKGROUND) > 12
        inside = alpha & unlike
        bare = inside & (delta_e(crop, BACKGROUND) < 5)
        out[name] = float(bare.sum() / max(1, inside.sum()))
    return out


def patches(sheet: Sheet, painted: Image.Image, far: float = 10.0) -> dict[str, float]:
    """For each piece, the share of its inside that, with its colours restored and smoothed over
    about a unit so the texture evens out, is far from the colour drawn there: high when the
    painter added something, like a stray patch."""
    out = {}
    for name, flat in sheet.pieces.items():
        restored = np.asarray(restore(sheet.crop(painted, name), flat.image), dtype=np.float64)
        nearest, main, _ = regions(flat.image)
        inside = np.asarray(flat.image.getchannel("A").filter(ImageFilter.MinFilter(7))) > 250
        off = np.zeros(inside.shape, dtype=bool)
        for i, colour in enumerate(main):
            region = inside & (nearest == i)
            if region.sum() < 50:
                continue
            smooth = _blur(restored, region.astype(np.float64), sheet.scale)
            off |= region & (delta_e(smooth, colour) > far)
        out[name] = float(off.sum() / max(1, inside.sum()))
    return out
