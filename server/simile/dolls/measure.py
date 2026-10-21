"""How close a painted figure's colours are to its `Appearance`, and pulling them back.

A whole painting has no map of its regions, so each colour is looked for in the rows it should be
in: the band of the figure where it shows in that pose.
"""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from simile.dolls.colour import cielab, delta_e_lab, from_cielab, hex_of, rgb
from simile.schema import Appearance

BANDS = {
    "upright": {
        "hair": (0.0, 0.32),
        "skin": (0.08, 0.75),
        "top": (0.35, 0.78),
        "bottom": (0.6, 0.97),
        "shoe": (0.85, 1.0),
    },
    "climb": {
        "hair": (0.08, 0.45),
        "skin": (0.0, 0.45),
        "top": (0.3, 0.72),
        "bottom": (0.55, 0.97),
        "shoe": (0.8, 1.0),
    },
}
"""Where each colour is looked for, as fractions of the figure's height from its top: standing,
walking, running or sitting, with the head almost half of it, or climbing with the hands up."""
FIELDS = {
    "skin": "skin",
    "hair": "hair_colour",
    "top": "top_colour",
    "bottom": "bottom_colour",
    "shoe": "shoe_colour",
}
LEAST = 0.04
"""The share of its band a colour must cover to be found there."""
WITHIN = 32.0
"""Further than this from the colour asked for, what was found is something else."""
FADE = (8.0, 18.0)
"""A painted colour's shades: pixels this far from it move with it fully, then less, then not."""
CLOSE = 6.0
"""What counts as matching the `Appearance`."""
KINDS = 6
"""The main colours a band is sorted into."""
SAMPLE = 20000
ROUNDS = 8
PASSES = 3
FACE_SKIN = 14.0
"""Within this of the skin asked for, CIEDE2000, a pixel is skin."""
FACE_DEPTH = 0.38
"""The share of the figure, from the top, the face is looked for in."""
FACE = ((0.45, 0.9), (0.15, 0.7))
"""Where the face is in the box round the skin of the head, across and down: in front of the
ear and the hair, which a figure turned to the right shows behind, and above the chin."""
FACE_FAR = 16.0
"""Further than this from the skin, a pixel on the face is something else painted on it."""
INK = 35.0
"""Lightness below which a pixel is the outline, an eye, a brow or dark glasses."""
DENSE = 0.3
MARKS = 0.05
"""The share of the face in such patches that counts as marked."""


@dataclass(frozen=True)
class Swatch:
    want: str
    got: str
    delta_e: float
    share: float


Anchors = dict[str, tuple[NDArray[np.float64], NDArray[np.float64]]]
"""Each colour's painted and wanted CIELAB."""


def opaque(figure: Image.Image) -> NDArray[np.bool_]:
    return np.asarray(figure.getchannel("A")) > 200


def bands(figure: Image.Image, layout: str) -> dict[str, NDArray[np.float64]]:
    """Each colour's rows in `BANDS[layout]`, 1 inside its band and fading out over a tenth of
    the figure's height."""
    solid = opaque(figure)
    found = np.flatnonzero(solid.any(axis=1))
    top, bottom = (found[0], found[-1]) if len(found) else (0, solid.shape[0] - 1)
    height = bottom - top + 1
    y = np.arange(solid.shape[0], dtype=np.float64)[:, None]
    out = {}
    for name, (start, end) in BANDS[layout].items():
        first, last = top + start * height, top + end * height
        outside = np.maximum(first - y, y - last)
        fade = np.clip(1 - outside / max(1.0, 0.1 * height), 0, 1)
        out[name] = np.broadcast_to(fade, solid.shape).copy()
    return out


def typical(
    lab: NDArray[np.float64], target: NDArray[np.float64], others: list[NDArray[np.float64]]
) -> tuple[NDArray, float]:
    """The colour painted for `target`: the middle of the colours nearer it than any of the
    `others` wanted, lit and shaded alike, if they cover `LEAST` of `lab`; or else, of the main
    colours in `lab`, the nearest. And its share of `lab`."""
    if not len(lab):
        return np.full(3, np.nan), 0.0
    distance = delta_e_lab(lab, target)
    mine = distance <= WITHIN
    for other in others:
        mine &= distance <= delta_e_lab(lab, other)
    if mine.mean() >= LEAST:
        return np.median(lab[mine], axis=0), float(mine.mean())
    centres, shares = main_colours(lab)
    found = shares >= LEAST
    if not found.any():
        found = shares > 0
    best = int(np.argmin(np.where(found, delta_e_lab(centres, target), np.inf)))
    return centres[best], float(shares[best])


def main_colours(lab: NDArray[np.float64], k: int = KINDS) -> tuple[NDArray, NDArray]:
    """`lab`'s colours in `k` clusters, k-means from the most different: their middles and
    shares."""
    sample = lab[:: max(1, len(lab) // SAMPLE)]
    centres = [np.median(sample, axis=0)]
    for _ in range(1, min(k, len(sample))):
        far = np.min([np.linalg.norm(sample - c, axis=1) for c in centres], axis=0)
        centres.append(sample[int(np.argmax(far))])
    centres = np.array(centres)
    for _ in range(ROUNDS):
        nearest = np.argmin([np.linalg.norm(sample - c, axis=1) for c in centres], axis=0)
        centres = np.array(
            [
                np.median(sample[nearest == i], axis=0) if (nearest == i).any() else c
                for i, c in enumerate(centres)
            ]
        )
    nearest = np.argmin([np.linalg.norm(lab - c, axis=1) for c in centres], axis=0)
    return centres, np.bincount(nearest, minlength=len(centres)) / len(lab)


def wanted(appearance: Appearance) -> dict[str, NDArray[np.float64]]:
    return {
        name: cielab(np.array(rgb(getattr(appearance, field)), dtype=np.float64))
        for name, field in FIELDS.items()
    }


def anchors(figure: Image.Image, appearance: Appearance, layout: str = "upright") -> Anchors:
    """Each of the `Appearance`'s colours the figure shows, and what was painted for it in its
    band."""
    lab = cielab(np.asarray(figure.convert("RGB"), dtype=np.float64))
    solid = opaque(figure)
    rows = bands(figure, layout)
    out = {}
    colours = wanted(appearance)
    for name, target in colours.items():
        if name in hidden(appearance):
            continue
        others = [c for n, c in colours.items() if n != name]
        got, _ = typical(lab[solid & (rows[name] >= 1)], target, others)
        if not np.isnan(got).any() and delta_e_lab(got, target) <= WITHIN:
            out[name] = (got, target)
    return out


def swatches(figure: Image.Image, appearance: Appearance, layout: str = "upright") -> dict:
    """Each colour as wanted, as painted, and how far apart they are, CIEDE2000."""
    lab = cielab(np.asarray(figure.convert("RGB"), dtype=np.float64))
    solid = opaque(figure)
    rows = bands(figure, layout)
    out = {}
    colours = wanted(appearance)
    for name, target in colours.items():
        others = [c for n, c in colours.items() if n != name]
        got, share = typical(lab[solid & (rows[name] >= 1)], target, others)
        want = hex_of(from_cielab(target))
        if np.isnan(got).any():
            out[name] = Swatch(want, "", float("inf"), 0.0)
        else:
            far = round(float(delta_e_lab(got, target)), 1)
            out[name] = Swatch(want, hex_of(from_cielab(got)), far, round(share, 3))
    return out


def worst(found: dict[str, Swatch], hidden: frozenset[str] = frozenset()) -> float:
    return max((s.delta_e for name, s in found.items() if name not in hidden), default=0.0)


def hidden(appearance: Appearance) -> frozenset[str]:
    """Colours a figure may not show: hair under a cap or beanie, or none at all."""
    worn = {a.value for a in appearance.accessories}
    if appearance.hair_style.value == "bald" or worn & {"cap", "beanie"}:
        return frozenset({"hair"})
    return frozenset()


def matched(figure: Image.Image, found: Anchors, layout: str = "upright") -> Image.Image:
    """The figure with each painted colour moved to the wanted one, by one shift in CIELAB, so
    its shading stays. A pixel moves with the painted colour nearest it, among those whose band
    it's in, and less the further it is from it."""
    pixels = np.asarray(figure.convert("RGBA"), dtype=np.float64)
    lab = cielab(pixels[..., :3])
    rows = bands(figure, layout)
    names = list(found)
    if not names:
        return figure.copy()
    distance = np.stack([delta_e_lab(lab, found[n][0]) for n in names])
    distance[np.stack([rows[n] <= 0 for n in names])] = np.inf
    nearest = distance.argmin(axis=0)
    shift = np.zeros_like(lab)
    low, high = FADE
    for i, name in enumerate(names):
        got, target = found[name]
        mine = nearest == i
        weight = np.clip((high - distance[i]) / (high - low), 0, 1) * rows[name] * mine
        shift += (target - got) * weight[..., None]
    out = pixels.copy()
    out[..., :3] = np.clip(from_cielab(lab + shift), 0, 255)
    return Image.fromarray(np.round(out).astype(np.uint8), "RGBA")


def pulled(figure: Image.Image, appearance: Appearance, layout: str = "upright") -> Image.Image:
    """The figure `matched` to the `Appearance` a few times over: a colour FLUX painted nearer
    another one asked for is first measured with it, and comes right once that one has moved."""
    for _ in range(PASSES):
        figure = matched(figure, anchors(figure, appearance, layout), layout)
    return figure


def face_marks(figure: Image.Image, appearance: Appearance) -> float:
    """The share of the face painted in patches far from the skin that aren't ink: the face is
    the front of the thick of the skin in the top of the figure, and lines and specks thinner
    than a hundredth of its height don't count."""
    lab = cielab(np.asarray(figure.convert("RGB"), dtype=np.float64))
    solid = opaque(figure)
    rows = np.flatnonzero(solid.any(axis=1))
    if not len(rows):
        return 0.0
    top, bottom = int(rows[0]), int(rows[-1])
    far = delta_e_lab(lab, wanted(appearance)["skin"])
    near = solid & (far < FACE_SKIN)
    near[top + int(FACE_DEPTH * (bottom - top)) :] = False
    if not near.any():
        return 0.0
    x, w = dense(near.sum(axis=0))
    y, h = dense(near[:, x : x + w].sum(axis=1))
    box = np.zeros_like(solid)
    box[
        y + int(FACE[1][0] * h) : y + int(FACE[1][1] * h),
        x + int(FACE[0][0] * w) : x + int(FACE[0][1] * w),
    ] = True
    odd = box & solid & (far >= FACE_FAR) & (lab[..., 0] >= INK)
    return float(opened(odd, max(1, round(0.01 * (bottom - top)))).sum() / max(box.sum(), 1))


def dense(counts: NDArray[np.int64]) -> tuple[int, int]:
    """Where `counts` is at least `DENSE` of its most, from the first such place to the last,
    and how far: the face, without a stray ear, hand or lock of hair."""
    found = np.flatnonzero(counts >= DENSE * counts.max())
    return int(found[0]), int(found[-1] - found[0] + 1)


def opened(mask: NDArray[np.bool_], r: int) -> NDArray[np.bool_]:
    """`mask` without anything narrower than `2 r + 1` pixels."""
    shifts = [(dy, dx) for dy in range(-r, r + 1) for dx in range(-r, r + 1)]
    padded = np.pad(mask, r)
    h, w = mask.shape
    eroded = np.all([padded[r + dy : r + dy + h, r + dx : r + dx + w] for dy, dx in shifts], axis=0)
    padded = np.pad(eroded, r)
    return np.any([padded[r + dy : r + dy + h, r + dx : r + dx + w] for dy, dx in shifts], axis=0)
