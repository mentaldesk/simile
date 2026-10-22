"""The player with bionics fitted, in every combination of the hydraulic legs, the datajack and the
infrared eye. Each frame is an edit of the same frame one bionic short, the whole player's at the
root, so a part looks the same in every combination it's in and every pose keeps the player's."""

from collections.abc import Iterable
from itertools import combinations

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageFilter

from simile.dolls.colour import cielab
from simile.dolls.figure import EDITS, FACE, styled, touching
from simile.dolls.words import described
from simile.schema import PLAYER_ID, Appearance
from simile.schema.player import Bionic

FITTED = (Bionic.HYDRAULIC_LEGS, Bionic.DATAJACK, Bionic.INFRARED_EYE)
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
        "the eye nearer the ear replaced by a bionic infrared eye built into the face: a round "
        "lens glowing bright red, set into the eye socket and ringed by a thin chrome edge, about "
        "the size of the other eye, with no frame, arm or strap reaching round the head. The other "
        "eye, beside the nose, stays a plain dark dot eye, and the skin around both eyes is clean "
        "and unchanged"
    ),
}
KEPT = {
    Bionic.HYDRAULIC_LEGS: "the bionic hydraulic legs below the shorts",
    Bionic.DATAJACK: "the chrome datajack at the neck with its light still bright green",
    Bionic.INFRARED_EYE: "the red bionic eye",
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
"""Where the shorts are, down a standing figure with the hydraulic legs: the bottom colour's
`measure.CORES`, since the shins are steel."""
LENS = (40.0, 15.0)
"""The red lens: a* above the first and lightness above the second, in the top half."""
LIGHT = (-30.0, 15.0)
"""The datajack's green light: a* below the first, b* above the second."""
LEAST = {Bionic.HYDRAULIC_LEGS: 0.06, Bionic.DATAJACK: 0.0007, Bionic.INFRARED_EYE: 0.002}
"""The share of a frame, or of its legs for the legs, a part must cover to be there."""
OTHER_EYE = 0.25
"""A second red patch this big against the first is the other eye painted red."""
RIM = 0.012
"""How far round the lens, in the figure's heights, its rim reaches: the face check spares it."""
PALETTE = np.array(
    [[lightness, 0.0, 0.0] for lightness in range(35, 95, 10)]
    + [[48.0, 70.0, 55.0], [80.0, -70.0, 65.0]]
)
"""The parts' colours in CIELAB, steel greys, the lens and the light, which a frame may show
although the whole player's standing figure doesn't."""


def figure_id(fitted: Iterable[Bionic]) -> str:
    """The figure for a body with `fitted`: `player` with none, `player_legs_eye` and so on."""
    have = set(fitted)
    return "_".join([PLAYER_ID, *(NAMES[b] for b in FITTED if b in have)])


def faces(frame: str) -> bool:
    return frame == "stand" or EDITS[frame].face


def shows(bionic: Bionic, frame: str) -> bool:
    """Whether `frame` shows the part: the eye isn't seen from behind."""
    return bionic != Bionic.INFRARED_EYE or faces(frame)


def edit_prompt(frame: str, combination: Combination, appearance: Appearance) -> str:
    """Adds the combination's last part to the same frame painted with the rest of it."""
    *before, part = combination
    words = described(appearance, PLAYER_ID)
    if Bionic.HYDRAULIC_LEGS in combination:
        words = words.replace(" trousers ", " shorts ")
    kept = [KEPT[b] for b in before if shows(b, frame)]
    keep = f" Keep {' and '.join(kept)} exactly as they are." if kept else ""
    face = ""
    if faces(frame):
        face = f" {EYE_FACE if Bionic.INFRARED_EYE in combination else FACE}"
    return styled(
        "Redraw image 1 with the same character, unchanged in every other detail and the same "
        f"size, in exactly the same pose and view, now with {WORDS[part]}.{keep} {words}{face} "
        "Keep the background plain light grey."
    )


def regions(figure: Image.Image) -> tuple[NDArray[np.bool_], NDArray[np.float64]]:
    """The opaque figure, and how far down it each row is, 0 at the crown and 1 at the soles."""
    solid = np.asarray(figure.getchannel("A")) > 200
    rows = np.flatnonzero(solid.any(axis=1))
    top, bottom = (rows[0], rows[-1]) if len(rows) else (0, solid.shape[0] - 1)
    down = (np.arange(solid.shape[0], dtype=np.float64) - top) / max(1, bottom - top)
    return solid, np.broadcast_to(down[:, None], solid.shape)


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


def patches(mask: NDArray[np.bool_]) -> list[int]:
    """The sizes of `mask`'s patches, biggest first."""
    left = mask.copy()
    sizes = []
    while left.any():
        y, x = np.argwhere(left)[0]
        patch = touching(left, int(x), int(y))
        sizes.append(int(patch.sum()))
        left &= ~patch
    return sorted(sizes, reverse=True)


def missing(figure: Image.Image, combination: Combination, frame: str) -> list[str]:
    """The parts `frame` should show but doesn't, and `two eyes` if both are painted red."""
    found = parts(figure)
    solid, down = regions(figure)
    out = []
    for bionic in combination:
        if not shows(bionic, frame):
            continue
        whole = solid & (down >= LEGS) if bionic == Bionic.HYDRAULIC_LEGS else solid
        if found[bionic].sum() < LEAST[bionic] * whole.sum():
            out.append(NAMES[bionic])
        elif bionic == Bionic.INFRARED_EYE:
            sizes = patches(found[bionic])
            if len(sizes) > 1 and sizes[1] >= OTHER_EYE * sizes[0]:
                out.append("two eyes")
    return out


def spared(figure: Image.Image) -> NDArray[np.bool_]:
    """The bionic eye and its rim, which the face check doesn't count as painted over."""
    lens = parts(figure)[Bionic.INFRARED_EYE]
    solid, _ = regions(figure)
    rows = np.flatnonzero(solid.any(axis=1))
    reach = max(1, round(RIM * (rows[-1] - rows[0]))) if len(rows) else 1
    grown = Image.fromarray(lens.astype(np.uint8) * 255).filter(
        ImageFilter.MaxFilter(2 * reach + 1)
    )
    return np.asarray(grown) > 0
