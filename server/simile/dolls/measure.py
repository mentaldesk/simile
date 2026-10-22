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
CORES = {
    "hair": (0.0, 0.15),
    "skin": (0.12, 0.33),
    "top": (0.36, 0.6),
    "bottom": (0.75, 0.9),
    "shoe": (0.93, 1.0),
}
"""Where each colour is found in a standing figure, its band's middle, clear of the others: the
crown, the face, the chest, the shins and the shoes."""
LEAST = 0.04
"""The share of its band a colour must cover to be found there."""
NEAR_BEST = 6.0
"""How much further from the colour asked for than the nearest main colour a bigger one may be
and still be taken for it, as the lit side of a face beside its shadow is."""
FOLLOW = 12.0
"""How far a pose's colour may be from the standing figure's, CIEDE2000, and be the same thing."""
LOST = 0.003
"""The share of a pose a colour of the standing figure must cover to be found in it."""
NEUTRAL = 12.0
"""Main colours further than this from every one asked for, such as a backpack's, stay put."""
STRAY = 12.0
"""How far a main colour of a pose may be from every one of the standing figure's."""
STRAY_LEAST = 0.02
STRAYS = 0.05
"""The share of a pose in such colours that counts as off the standing figure."""
WITHIN = 32.0
"""Further than this from the colour asked for, what was found is something else."""
FADE = (8.0, 18.0)
"""A painted colour's shades: pixels this far from it move with it fully, then less, then not."""
CLOSE = 6.0
"""What counts as matching the `Appearance`."""
KINDS = 6
"""The main colours a band is sorted into, and twice as many for a whole figure."""
SAMPLE = 20000
ROUNDS = 8
PASSES = 2
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


def core(
    figure: Image.Image, name: str, cores: dict[str, tuple[float, float]] = CORES
) -> NDArray[np.bool_]:
    solid = opaque(figure)
    rows = np.flatnonzero(solid.any(axis=1))
    top, height = rows[0], rows[-1] - rows[0] + 1
    start, end = cores[name]
    out = np.zeros_like(solid)
    out[top + int(start * height) : top + int(np.ceil(end * height))] = True
    return out & solid


def chosen(lab: NDArray[np.float64], target: NDArray[np.float64]) -> tuple[NDArray, float]:
    """Of `lab`'s main colours covering at least `LEAST` of it and within `WITHIN` of `target`,
    the biggest of those nearly as near it as the nearest; and its share. NaN if none."""
    if len(lab) < 20:
        return np.full(3, np.nan), 0.0
    centres, shares = main_colours(lab)
    far = np.where(shares >= LEAST, delta_e_lab(centres, target), np.inf)
    if far.min() > WITHIN:
        return np.full(3, np.nan), 0.0
    pick = int(np.argmax(np.where(far <= far.min() + NEAR_BEST, shares, -1)))
    return centres[pick], float(shares[pick])


def identify(figure: Image.Image, appearance: Appearance) -> Anchors:
    """Each colour a standing figure shows, as painted, from the middle of its band, and the
    colour asked for. Hair a cap hides isn't looked for, or the face would be taken for it."""
    lab = cielab(np.asarray(figure.convert("RGB"), dtype=np.float64))
    out = {}
    for name, target in wanted(appearance).items():
        if name in hidden(appearance):
            continue
        got, _ = chosen(lab[core(figure, name)], target)
        if not np.isnan(got).any():
            out[name] = (got, target)
    return out


def follow(
    figure: Image.Image, painted: dict[str, NDArray], appearance: Appearance, layout: str
) -> Anchors:
    """Each colour as the standing figure was `painted`, found again in a pose: the middle of
    what's within `FOLLOW` of it in its band, if there's enough of it."""
    lab = cielab(np.asarray(figure.convert("RGB"), dtype=np.float64))
    solid = opaque(figure)
    rows = bands(figure, layout)
    colours = wanted(appearance)
    out = {}
    for name, colour in painted.items():
        here = lab[solid & (rows[name] > 0)]
        near = delta_e_lab(here, colour) < FOLLOW
        if near.sum() >= LOST * solid.sum():
            out[name] = (np.median(here[near], axis=0), colours[name])
    return out


def swatches(
    figure: Image.Image,
    appearance: Appearance,
    layout: str = "upright",
    cores: dict[str, tuple[float, float]] = CORES,
) -> dict:
    """Each colour as wanted, as painted, and how far apart they are, CIEDE2000: in a standing
    figure from the middle of its band, its `cores`, in another pose from all of it."""
    lab = cielab(np.asarray(figure.convert("RGB"), dtype=np.float64))
    rows = bands(figure, layout)
    out = {}
    for name, target in wanted(appearance).items():
        upright = layout == "upright"
        where = core(figure, name, cores) if upright else opaque(figure) & (rows[name] >= 1)
        got, share = chosen(lab[where], target)
        want = hex_of(from_cielab(target))
        if np.isnan(got).any():
            out[name] = Swatch(want, "", float("inf"), 0.0)
        else:
            far = round(float(delta_e_lab(got, target)), 1)
            out[name] = Swatch(want, hex_of(from_cielab(got)), far, round(share, 3))
    return out


def kept(
    figure: Image.Image,
    fixed: Image.Image,
    painted: dict[str, NDArray],
    appearance: Appearance,
    layout: str,
) -> dict:
    """Each colour as `follow` found it in a pose `figure`, as painted, against the same pixels
    once `fixed`: how far each garment is from the colour asked for after matching."""
    before = cielab(np.asarray(figure.convert("RGB"), dtype=np.float64))
    after = cielab(np.asarray(fixed.convert("RGB"), dtype=np.float64))
    solid = opaque(figure)
    rows = bands(figure, layout)
    out = {}
    for name, colour in painted.items():
        target = wanted(appearance)[name]
        want = hex_of(from_cielab(target))
        mine = solid & (rows[name] > 0) & (delta_e_lab(before, colour) < FOLLOW)
        if mine.sum() < LOST * solid.sum():
            out[name] = Swatch(want, "", float("inf"), 0.0)
            continue
        got = np.median(after[mine], axis=0)
        far = round(float(delta_e_lab(got, target)), 1)
        out[name] = Swatch(want, hex_of(from_cielab(got)), far, round(float(mine.mean()), 3))
    return out


def strays(
    figure: Image.Image, standing: Image.Image, also: NDArray[np.float64] | None = None
) -> float:
    """The share of `figure` painted in main colours the standing figure hasn't got, each over
    `STRAY` from all of its and from any it may `also` show: a garment or a limb that came out,
    or was pulled, another colour."""
    mine = cielab(np.asarray(figure.convert("RGB"), dtype=np.float64)[opaque(figure)])
    theirs = cielab(np.asarray(standing.convert("RGB"), dtype=np.float64)[opaque(standing)])
    if not len(mine) or not len(theirs):
        return 0.0
    centres, shares = main_colours(mine, 2 * KINDS)
    known, _ = main_colours(theirs, 2 * KINDS)
    if also is not None:
        known = np.vstack([known, also])
    far = np.array([delta_e_lab(known, c).min() for c in centres])
    return round(float(shares[(far > STRAY) & (shares >= STRAY_LEAST)].sum()), 3)


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
    it's in and the figure's other main colours, which stay put, and less the further it is."""
    pixels = np.asarray(figure.convert("RGBA"), dtype=np.float64)
    lab = cielab(pixels[..., :3])
    solid = opaque(figure)
    rows = bands(figure, layout)
    names = list(found)
    if not names or not solid.any():
        return figure.copy()
    gots = np.array([found[n][0] for n in names])
    others, _ = main_colours(lab[solid], 2 * KINDS)
    others = [c for c in others if delta_e_lab(gots, c).min() > NEUTRAL]
    distance = np.stack([delta_e_lab(lab, g) for g in gots] + [delta_e_lab(lab, c) for c in others])
    distance[: len(names)][np.stack([rows[n] <= 0 for n in names])] = np.inf
    nearest = distance.argmin(axis=0)
    shift = np.zeros_like(lab)
    low, high = FADE
    for i, name in enumerate(names):
        got, target = found[name]
        weight = np.clip((high - distance[i]) / (high - low), 0, 1) * rows[name] * (nearest == i)
        shift += (target - got) * weight[..., None]
    out = pixels.copy()
    out[..., :3] = np.clip(from_cielab(lab + shift), 0, 255)
    return Image.fromarray(np.round(out).astype(np.uint8), "RGBA")


def pulled(
    figure: Image.Image,
    appearance: Appearance,
    layout: str = "upright",
    painted: dict[str, NDArray] | None = None,
) -> Image.Image:
    """The figure `matched` to the `Appearance`: a standing figure's colours found in the middle
    of their bands, twice over, and another pose's by following how the standing figure was
    `painted`, so every pose moves the same garment the same way."""
    if painted is not None:
        return matched(figure, follow(figure, painted, appearance, layout), layout)
    for _ in range(PASSES):
        figure = matched(figure, identify(figure, appearance), layout)
    return figure


def face_marks(
    figure: Image.Image, appearance: Appearance, spared: NDArray[np.bool_] | None = None
) -> float:
    """The share of the face painted in patches far from the skin that aren't ink or `spared`:
    the face is the front of the thick of the skin in the top of the figure, and lines and
    specks thinner than a hundredth of its height don't count."""
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
    if spared is not None:
        odd &= ~spared
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
