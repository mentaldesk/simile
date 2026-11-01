"""The player with each combination of bionics: each part painted once over the player's frames."""

import re
from collections.abc import Iterable
from itertools import combinations

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageFilter

from simile.dolls.colour import cielab, delta_e_lab
from simile.dolls.figure import ASLEEP, EDITS, FACE, styled, touching
from simile.dolls.sprites import head
from simile.dolls.words import described
from simile.schema import PLAYER_ID, Appearance
from simile.schema.player import BIONIC_LEGS as LEGS_LINE
from simile.schema.player import SPRING_FEET as FEET_LINE
from simile.schema.player import Bionic

VERSION = 1
"""How the parts are laid over the whole player: a new one lays them again."""
LEGS_PART, FEET = Bionic.BIONIC_LEGS, Bionic.SPRING_FEET
FITTED = (LEGS_PART, FEET, Bionic.DATAJACK, Bionic.INFRARED_EYE)
EYE = Bionic.INFRARED_EYE
NAMES = {
    LEGS_PART: "bionic_legs",
    FEET: "feet",
    Bionic.DATAJACK: "datajack",
    Bionic.INFRARED_EYE: "eye",
}
SHOWN_AS = (
    dict.fromkeys(LEGS_LINE, LEGS_PART)
    | dict.fromkeys(FEET_LINE, FEET)
    | {Bionic.DATAJACK: Bionic.DATAJACK, EYE: EYE}
)
"""The part a figure shows for each bionic: every grade of a line looks alike."""
LOWER = (LEGS_PART, FEET)
"""Parts of the lower body, painted together as one layer."""
type Combination = tuple[Bionic, ...]


COMBINATIONS: tuple[Combination, ...] = tuple(
    c for n in range(1, len(FITTED) + 1) for c in combinations(FITTED, n)
)
"""Every combination of bionics a figure shows but none, fewest first, each in `FITTED`'s order."""


def shown(fitted: Iterable[Bionic]) -> Combination:
    """The parts a body's figure shows."""
    have = {SHOWN_AS[b] for b in fitted if b in SHOWN_AS}
    return tuple(b for b in FITTED if b in have)


def layers(combination: Combination) -> list[Combination]:
    """What's laid over the whole player for `combination`: the lower body, then each other part."""
    lower = tuple(b for b in combination if b in LOWER)
    return ([lower] if lower else []) + [(b,) for b in combination if b not in LOWER]


LAYERS: tuple[Combination, ...] = tuple(
    sorted(
        {layer for c in COMBINATIONS for layer in layers(c)},
        key=lambda c: (len(c), FITTED.index(c[0])),
    )
)
"""Each layer painted, as an edit of the whole player's frame or of `layer[:-1]`'s painting."""
WORDS = {
    LEGS_PART: (
        "both legs replaced by sleek bionic legs: the trousers now end above the knees as shorts, "
        "and below them each lower leg is a smooth streamlined robot leg of rounded steel-grey "
        "armour plates, like a racing robot's, with a black rubber joint at the knee and at the "
        "ankle, ending in the same white sneakers"
    ),
    FEET: (
        "both feet replaced by bionic spring feet, in place of the sneakers: below each ankle, "
        "a flat steel-grey metal foot plate shaped like a shoe, with a chunky bright yellow coil "
        "spring between the ankle and the heel. Everything above the ankles, the legs and their "
        "clothes, stays exactly as it is"
    ),
    Bionic.DATAJACK: (
        "a datajack port set into the skin at the back of the neck, just under the hair at the "
        "nape: a chunky round chrome socket with a bright green light in its middle, and no "
        "collar, band or ring around the neck"
    ),
    Bionic.INFRARED_EYE: (
        "the eye nearer the ear replaced by a small bionic infrared eye, no bigger than the other "
        "eye: a bright red lens with a thin chrome rim. The other eye, beside the nose, stays a "
        "plain dark dot eye, and the skin around both eyes is clean and unchanged"
    ),
}
EYE_FACE = (
    "The face is clean, with a small smile and no smudges on it: one bright red bionic eye nearer "
    "the ear and one plain dark dot eye beside the nose."
)
ASLEEP_EYE = (
    "The face is clean and peaceful, asleep, with no smudges on it: one bright red bionic eye in "
    "place of the upper eye, still open, and the lower eye closed as a small curved line."
)
ASLEEP_WORDS = {
    EYE: (
        "the upper of the two closed eyes replaced, right where it is on the face, by a small "
        "bionic infrared eye no bigger than the other eye: a bright red lens with a thin chrome "
        "rim. The lower eye stays closed, asleep, as a small curved line, and the skin around "
        "both eyes and the ear is clean and unchanged"
    )
}
"""`WORDS` for a figure asleep."""
METAL = (12.0, 40.0, 88.0)
"""Steel and chrome, CIELAB: chroma below the first, lightness between the others."""
LEGS_FROM = 0.6
"""Where the legs start, down the figure."""
SHORTS = (0.62, 0.7)
"""The bottom colour's `measure.CORES` with the bionic legs, whose shins are steel."""
SPRING = (55.0, 25.0, 50.0)
"""The yellow spring: b* above the first, a* below the second, lightness above the third."""
LENS = (40.0, 15.0)
"""The red lens: a* above the first and lightness above the second, in the top half."""
LIGHT = (-30.0, 15.0)
"""The datajack's green light: a* below the first, b* above the second."""
LEAST = {
    LEGS_PART: 0.12,
    FEET: 0.006,
    Bionic.DATAJACK: 0.001,
    Bionic.INFRARED_EYE: 0.002,
}
"""The share of a frame, or of its legs for the legs, a part must cover to be there."""
LENS_WIDE = 0.17
"""The widest the lens may be, as a share of the head's width: the walk's is about 0.15."""
OTHER_EYE = 0.25
"""A second red patch this big against the first is the other eye painted red."""
RIM = 0.012
"""How far round the lens, in the figure's heights, its rim reaches: the face check spares it."""
PALETTE = np.array(
    [[lightness, 0.0, 0.0] for lightness in range(35, 95, 10)]
    + [[48.0, 70.0, 55.0], [80.0, -70.0, 65.0], [85.0, 0.0, 85.0]]
)
"""The parts' colours in CIELAB, which a frame may show although the whole player doesn't."""
CHANGED = 10.0
"""How far a pixel of a part's frame is from the whole player's, CIEDE2000, to be changed."""
SHORTS_FROM = 0.5
"""How far down the figure the legs' changes start: the shorts' hem is above the knees."""
REACH = {Bionic.DATAJACK: 0.06, Bionic.INFRARED_EYE: 0.03}
"""How far from its light or lens, in the figure's heights, a part's changes are its own."""
GROW = 6
"""Pixels round what changed laid with it, for its outline."""
FEATHER = 2.0
"""The blur, in pixels, over the edge of what's laid."""


def figure_id(fitted: Iterable[Bionic]) -> str:
    """The figure for a body with `fitted`: `player` with none, `player_feet_eye` and so on."""
    return "_".join([PLAYER_ID, *(NAMES[b] for b in shown(fitted))])


def hides(fitted: Combination) -> frozenset[str]:
    """The `Appearance`'s colours a figure with `fitted` lacks: the feet replace the shoes."""
    return frozenset({"shoe"}) if FEET in fitted else frozenset()


def faces(frame: str) -> bool:
    return frame == "stand" or EDITS[frame].face


def asleep(frame: str) -> bool:
    return frame != "stand" and EDITS[frame].lying


def shows(bionic: Bionic, frame: str) -> bool:
    """Whether `frame` shows the part: the eye isn't seen from behind."""
    return bionic != Bionic.INFRARED_EYE or faces(frame)


def edit_prompt(frame: str, bionic: Bionic, appearance: Appearance, over: Combination = ()) -> str:
    """Adds `bionic` to the whole player's `frame`, with the parts `over` it already shows."""
    words = described(appearance, PLAYER_ID)
    if LEGS_PART in {bionic, *over}:
        words = words.replace(" trousers ", " shorts ")
    if bionic == FEET:
        words = re.sub(r", ([^,]+?) (trousers|shorts) and [^,.]+? sneakers", r" and \1 \2", words)
    part = ASLEEP_WORDS.get(bionic, WORDS[bionic]) if asleep(frame) else WORDS[bionic]
    face = ""
    if faces(frame):
        eye = bionic == Bionic.INFRARED_EYE
        face = (ASLEEP_EYE if eye else ASLEEP) if asleep(frame) else (EYE_FACE if eye else FACE)
        face = f" {face}"
    return styled(
        "Redraw image 1 with the same character, unchanged in every other detail and the same "
        f"size, in exactly the same pose and view, now with {part}. {words}{face} "
        "Keep the background plain light grey."
    )


def regions(figure: Image.Image) -> tuple[NDArray[np.bool_], NDArray[np.float64]]:
    """The opaque figure, and how far down it each row is, 0 at the crown and 1 at the soles."""
    solid = np.asarray(figure.getchannel("A")) > 200
    rows = np.flatnonzero(solid.any(axis=1))
    top, bottom = (rows[0], rows[-1]) if len(rows) else (0, solid.shape[0] - 1)
    down = (np.arange(solid.shape[0], dtype=np.float64) - top) / max(1, bottom - top)
    return solid, np.broadcast_to(down[:, None], solid.shape)


def height(solid: NDArray[np.bool_]) -> int:
    rows = np.flatnonzero(solid.any(axis=1))
    return int(rows[-1] - rows[0]) if len(rows) else 0


def parts(figure: Image.Image) -> dict[Bionic, NDArray[np.bool_]]:
    """Where each part's colours are: steel in the legs, the green light and the red lens."""
    solid, down = regions(figure)
    lab = cielab(np.asarray(figure.convert("RGB"), dtype=np.float64))
    light, a, b = lab[..., 0], lab[..., 1], lab[..., 2]
    metal = (np.hypot(a, b) < METAL[0]) & (light > METAL[1]) & (light < METAL[2])
    legs = solid & (down >= LEGS_FROM)
    spring = (b > SPRING[0]) & (a < SPRING[1]) & (light > SPRING[2])
    return {
        LEGS_PART: legs & metal,
        FEET: legs & spring,
        Bionic.DATAJACK: solid & (a < LIGHT[0]) & (b > LIGHT[1]),
        Bionic.INFRARED_EYE: solid & (a > LENS[0]) & (light > LENS[1]) & (down < 0.5),
    }


def patches(mask: NDArray[np.bool_]) -> list[NDArray[np.bool_]]:
    """`mask`'s patches, corners joining them, biggest first."""
    left = mask.copy()
    found = []
    while left.any():
        y, x = np.argwhere(left)[0]
        found.append(touching(left, int(x), int(y)))
        left &= ~found[-1]
    return sorted(found, key=lambda patch: -int(patch.sum()))


def missing(
    figure: Image.Image, combination: Combination, frame: str, least: float = 1.0
) -> list[str]:
    """What's wrong with the parts `frame` shows: one missing, two eyes, or an outsize eye."""
    found = parts(figure)
    solid, down = regions(figure)
    out = []
    for bionic in combination:
        if not shows(bionic, frame):
            continue
        whole = solid & (down >= LEGS_FROM) if bionic in LOWER else solid
        if found[bionic].sum() < least * LEAST[bionic] * whole.sum():
            out.append(NAMES[bionic])
        elif bionic == Bionic.INFRARED_EYE:
            lenses = patches(found[bionic])
            if len(lenses) > 1 and lenses[1].sum() >= OTHER_EYE * lenses[0].sum():
                out.append("two eyes")
            if lens_width(figure, lenses[0]) > LENS_WIDE / least:
                out.append("eye too big")
    return out


def lens_width(figure: Image.Image, lens: NDArray[np.bool_]) -> float:
    """How wide `lens` is, as a share of the head's width."""
    columns = np.flatnonzero(lens.any(axis=0))
    return (columns[-1] - columns[0] + 1) / max(head(figure)[1], 1)


def grown(mask: NDArray[np.bool_], by: int) -> NDArray[np.bool_]:
    image = Image.fromarray(mask.astype(np.uint8) * 255)
    return np.asarray(image.filter(ImageFilter.MaxFilter(2 * by + 1))) > 0


def spared(figure: Image.Image) -> NDArray[np.bool_]:
    """The bionic eye and its rim, which the face check doesn't count as painted over."""
    solid, _ = regions(figure)
    reach = max(1, round(RIM * height(solid)))
    return grown(parts(figure)[Bionic.INFRARED_EYE], reach)


def changed(whole: Image.Image, edit: Image.Image, layer: Combination) -> NDArray[np.bool_]:
    """Where the `edit` of the `whole` player's frame painted `layer`'s parts, with its outline."""
    a, b = np.asarray(whole.convert("RGBA")), np.asarray(edit.convert("RGBA"))
    solid, down = regions(edit)
    both = (a[..., 3] > 128) & (b[..., 3] > 128)
    far = delta_e_lab(cielab(a[..., :3].astype(np.float64)), cielab(b[..., :3].astype(np.float64)))
    diff = (np.abs(a[..., 3].astype(int) - b[..., 3].astype(int)) > 64) | (both & (far > CHANGED))
    found = parts(edit)
    seeds = [found[bionic] for bionic in layer]
    if layer[0] in LOWER:
        diff &= down >= SHORTS_FROM
    elif seeds[0].any():
        seeds = [patches(seeds[0])[0]]
        diff &= grown(seeds[0], round(REACH[layer[0]] * height(solid)))
    joined = grown(diff | np.logical_or.reduce(seeds), 2)
    keep = np.zeros_like(joined)
    for seed in seeds:
        for y, x in np.argwhere(seed)[:: max(1, int(seed.sum()) // 50)]:
            if not keep[y, x]:
                keep |= touching(joined, int(x), int(y))
    return grown(keep, GROW)


def laid(whole: Image.Image, layers: list[tuple[Image.Image, NDArray[np.bool_]]]) -> Image.Image:
    """The `whole` player's frame with each layer's frame where it says, feathered."""
    out = np.asarray(whole.convert("RGBA")).astype(np.float64)
    for edit, where in layers:
        soft = Image.fromarray(where.astype(np.uint8) * 255).filter(
            ImageFilter.GaussianBlur(FEATHER)
        )
        weight = (np.asarray(soft) / 255.0)[..., None]
        out = out * (1 - weight) + np.asarray(edit.convert("RGBA")).astype(np.float64) * weight
    return Image.fromarray(np.round(out).astype(np.uint8), "RGBA")
