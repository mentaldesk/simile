"""The player with each combination of bionics: each part painted once over the player's frames."""

from collections.abc import Iterable
from itertools import combinations

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageFilter

from simile.dolls.colour import cielab, delta_e_lab
from simile.dolls.figure import EDITS, FACE, styled, touching
from simile.dolls.sprites import head
from simile.dolls.words import described
from simile.schema import PLAYER_ID, Appearance
from simile.schema.player import Bionic

VERSION = 1
"""How the parts are laid over the whole player: a new one lays them again."""
FITTED = (Bionic.HYDRAULIC_LEGS, Bionic.DATAJACK, Bionic.INFRARED_EYE)
EYE = Bionic.INFRARED_EYE
NAMES = {Bionic.HYDRAULIC_LEGS: "legs", Bionic.DATAJACK: "datajack", Bionic.INFRARED_EYE: "eye"}
type Combination = tuple[Bionic, ...]
COMBINATIONS: tuple[Combination, ...] = tuple(
    c for n in range(1, len(FITTED) + 1) for c in combinations(FITTED, n)
)
"""Every combination of bionics but none, fewest first, each in `FITTED`'s order."""
WORDS = {
    Bionic.HYDRAULIC_LEGS: (
        "both legs replaced by bionic hydraulic legs: the trousers now end above the knees as "
        "shorts, and below them each lower leg is bare steel-grey machinery with a shiny chrome "
        "hydraulic piston down the shin and a round metal knee joint, ending in the same white "
        "sneakers"
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
METAL = (12.0, 40.0, 88.0)
"""Steel and chrome, CIELAB: chroma below the first, lightness between the others."""
LEGS = 0.6
"""Where the legs start, down the figure."""
SHORTS = (0.62, 0.7)
"""The bottom colour's `measure.CORES` with the hydraulic legs, whose shins are steel."""
LENS = (40.0, 15.0)
"""The red lens: a* above the first and lightness above the second, in the top half."""
LIGHT = (-30.0, 15.0)
"""The datajack's green light: a* below the first, b* above the second."""
LEAST = {Bionic.HYDRAULIC_LEGS: 0.12, Bionic.DATAJACK: 0.001, Bionic.INFRARED_EYE: 0.002}
"""The share of a frame, or of its legs for the legs, a part must cover to be there."""
LENS_WIDE = 0.17
"""The widest the lens may be, as a share of the head's width: the walk's is about 0.15."""
OTHER_EYE = 0.25
"""A second red patch this big against the first is the other eye painted red."""
RIM = 0.012
"""How far round the lens, in the figure's heights, its rim reaches: the face check spares it."""
PALETTE = np.array(
    [[lightness, 0.0, 0.0] for lightness in range(35, 95, 10)]
    + [[48.0, 70.0, 55.0], [80.0, -70.0, 65.0]]
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
    """The figure for a body with `fitted`: `player` with none, `player_legs_eye` and so on."""
    have = set(fitted)
    return "_".join([PLAYER_ID, *(NAMES[b] for b in FITTED if b in have)])


def faces(frame: str) -> bool:
    return frame == "stand" or EDITS[frame].face


def shows(bionic: Bionic, frame: str) -> bool:
    """Whether `frame` shows the part: the eye isn't seen from behind."""
    return bionic != Bionic.INFRARED_EYE or faces(frame)


def edit_prompt(frame: str, bionic: Bionic, appearance: Appearance) -> str:
    """Adds `bionic` to the whole player's `frame`."""
    words = described(appearance, PLAYER_ID)
    if bionic == Bionic.HYDRAULIC_LEGS:
        words = words.replace(" trousers ", " shorts ")
    face = ""
    if faces(frame):
        face = f" {EYE_FACE if bionic == Bionic.INFRARED_EYE else FACE}"
    return styled(
        "Redraw image 1 with the same character, unchanged in every other detail and the same "
        f"size, in exactly the same pose and view, now with {WORDS[bionic]}. {words}{face} "
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
    return {
        Bionic.HYDRAULIC_LEGS: solid & metal & (down >= LEGS),
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
        whole = solid & (down >= LEGS) if bionic == Bionic.HYDRAULIC_LEGS else solid
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


def changed(whole: Image.Image, edit: Image.Image, bionic: Bionic) -> NDArray[np.bool_]:
    """Where the `edit` of the `whole` player's frame painted `bionic`, with its outline."""
    a, b = np.asarray(whole.convert("RGBA")), np.asarray(edit.convert("RGBA"))
    solid, down = regions(edit)
    both = (a[..., 3] > 128) & (b[..., 3] > 128)
    far = delta_e_lab(cielab(a[..., :3].astype(np.float64)), cielab(b[..., :3].astype(np.float64)))
    diff = (np.abs(a[..., 3].astype(int) - b[..., 3].astype(int)) > 64) | (both & (far > CHANGED))
    seeds = parts(edit)[bionic]
    if bionic == Bionic.HYDRAULIC_LEGS:
        diff &= down >= SHORTS_FROM
    elif seeds.any():
        seeds = patches(seeds)[0]
        diff &= grown(seeds, round(REACH[bionic] * height(solid)))
    joined = grown(diff | seeds, 2)
    keep = np.zeros_like(joined)
    for y, x in np.argwhere(seeds)[:: max(1, int(seeds.sum()) // 50)]:
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
