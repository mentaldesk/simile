"""A resident painted whole, as #334's approach 1: standing from text in three-quarter view, and
every other pose an edit of that painting, so they stay the same person."""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageDraw, ImageFilter

from simile.dolls.words import described
from simile.papercraft.painter import NO_TEXT
from simile.schema import Appearance

SIZE = (768, 1024)
LOOK = (
    "hand-drawn 2D cartoon game art: smooth, even dark brown ink outlines of one steady weight, "
    "flat colour fills with simple soft shading, clean surfaces with no smudges, stains or "
    "grime, chunky rounded simplified shapes, bold readable silhouettes"
)
"""#334's approach 1 came out clean from #329's grimy words; this asks for it."""
BODY = (
    "The character has a very big round head, almost half their height, on a small short body "
    "with short legs, like the residents of a cartoon colony-building game."
)
FACE = "The face is clean, with simple dot eyes and a small smile, and no smudges on it."
ASLEEP = (
    "The face is clean and peaceful, asleep with both eyes closed as small curved lines, and no "
    "smudges on it."
)
STAND = (
    "A single full-body 2D game character sprite on a plain flat light grey background with "
    "nothing else in the picture: one resident of a modern southern Chinese tech city like "
    "Shenzhen, standing in a three-quarter view turned to the right, arms relaxed at the sides, "
    "feet apart. {persona}{who} {body} {face} Contemporary casual clothes."
)
SAME = (
    "Redraw image 1 with the same character, unchanged in every detail and the same size, in the "
    "same three-quarter view turned to the right, now "
)
INK = (58, 36, 28)
APRON = 0.6
"""Where an apron is, down the figure, under the middle of the hips."""
APRON_NEAR = 15.0
APRON_EDGE = 4
"""Pixels round the apron kept with it, for its outline."""


@dataclass(frozen=True)
class Pose:
    words: str
    base: str = "stand"
    """The frame it's an edit of."""
    bands: str = "upright"
    """Where each colour is in the figure: `measure.BANDS`."""
    legs: str | None = None
    """Painted over `base` with its legs redrawn roughly in this `LEGS` pose: FLUX draws a
    stride for every passing step it's asked for in words."""
    face: bool = True
    seated: bool = False
    """Sits on a seat: the client puts it there by where it sits."""
    lifted: str | None = None
    """In the air, as high as this frame's head: FLUX draws a running figure's knees up, so
    standing on its lowest foot would drop its head."""
    lying: bool = False
    """Lies on its side, head to the left: painted in landscape and measured turned head up."""


Leg = tuple[tuple[float, float], ...]
LEGS: dict[str, tuple[Leg, Leg]] = {
    "pass": (((0.0, 1.0),), ((0.07, 0.45), (-0.05, 0.78))),
}
"""Each leg, planted then lifted, as its knee and foot: across from under the hips in the figure's
heights, and down from the crotch to the ground as a share of the leg."""
GUIDED = (
    "Redraw image 1 as a finished drawing of the same character, unchanged in every detail and "
    "the same size, in the same three-quarter view turned to the right. Keep the pose of the "
    "legs exactly as they are roughly sketched in image 1: {legs}. The sketch only shows the "
    "pose: draw the legs cleanly and properly as the character's own trousers and shoes, with "
    "nothing of the sketch left."
)


EDITS = {
    "stride": Pose(
        SAME + "walking to the right in mid-stride: the left leg forward, the right leg back, "
        "the arms swinging."
    ),
    "pass": Pose(
        GUIDED.format(legs="one leg straight and planted, the other bent with its foot lifted"),
        legs="pass",
    ),
    "run": Pose(
        SAME + "running fast to the right, leaning forward: the left knee driven high in front, "
        "the right leg pushing off behind, both feet off the ground, the elbows bent and the "
        "arms pumping.",
        lifted="run_pass",
    ),
    "run_pass": Pose(
        "Redraw image 1 with the same character, unchanged in every detail and the same size, in "
        "the same three-quarter view turned to the right, with the legs exactly as they are, now "
        "running: the body leaning forward, the elbows bent and the arms pumping.",
        base="pass",
    ),
    "sit": Pose(
        SAME + "sitting with the knees bent forward and the hands resting on the knees, sitting "
        "in mid-air with nothing under them: no chair, no box, no seat.",
        seated=True,
    ),
    "climb": Pose(
        "Redraw image 1 with the same character, unchanged in every detail and the same size, "
        "now seen from directly behind: the back of the head and the back of the clothes, both "
        "hands raised above the head, empty and holding nothing, one knee raised as if stepping "
        "up, hanging in mid-air with nothing else drawn: no ladder, no steps, no rungs, no bar.",
        bands="climb",
        face=False,
    ),
    "lie": Pose(
        "Redraw image 1 with the same character, unchanged in every detail and the same size, "
        "now lying down asleep on their side, seen from the front, curled up: the body flat and "
        "level, the head on the left and the feet on the right, the knees bent and drawn up "
        "towards the tummy, the arms relaxed in front of the body, floating in mid-air with "
        "nothing under them: no bed, no pillow, no blanket, no mattress, no floor, no shadow.",
        lying=True,
    ),
}
"""Each pose as an edit of another painting: `base`, the standing one unless it says."""
STANDING = Pose(STAND)
"""The standing figure, painted from text."""
FRAMES = ("stand", *EDITS)
POSES = {
    "stand": ["stand"],
    "walk": ["stride", "pass", "stride", "pass"],
    "run": ["run", "run_pass", "run", "run_pass"],
    "sit": ["sit"],
    "climb": ["climb"],
    "lie": ["lie"],
}
"""The frames each pose plays, one after another through its cycle."""


def styled(subject: str) -> str:
    return f"{subject} Art style: {LOOK}.{NO_TEXT}"


def stand_prompt(appearance: Appearance, who: str | None, persona: str = "") -> str:
    return styled(
        STAND.format(
            persona=f"{persona} " if persona else "",
            who=described(appearance, who),
            body=BODY,
            face=FACE,
        )
    )


def edit_prompt(frame: str, appearance: Appearance, who: str | None) -> str:
    pose = EDITS[frame]
    face = f" {ASLEEP if pose.lying else FACE}" if pose.face else ""
    return styled(
        f"{pose.words} {described(appearance, who)}{face} Keep the background plain light grey."
    )


def legs_guide(
    painting: Image.Image, alpha: NDArray[np.uint8], appearance: Appearance, pose: str
) -> Image.Image:
    """The painting with its legs rubbed out and drawn again, roughly, in `LEGS[pose]`."""
    solid = alpha >= 128
    rows = np.flatnonzero(solid.any(axis=1))
    top, bottom = int(rows[0]), int(rows[-1])
    tall = bottom - top
    crotch = crotch_row(solid, top, bottom)
    cols = np.flatnonzero(solid[crotch:].any(axis=0))
    left, right = int(cols[0]), int(cols[-1])
    middle = float(np.flatnonzero(solid[crotch]).mean())
    out = painting.convert("RGB").copy()
    ground = tuple(int(v) for v in np.median(np.asarray(out)[:6].reshape(-1, 3), axis=0))
    draw = ImageDraw.Draw(out)
    draw.rectangle((left - 0.08 * tall, crotch, right + 0.08 * tall, bottom + 0.04 * tall), ground)
    leg = bottom - crotch
    width = max(6, round(0.08 * tall))
    foot, sole = 0.11 * tall, 0.065 * tall
    paths = [
        [(middle, crotch - 0.02 * tall)]
        + [(middle + x * tall, crotch + y * (leg - sole)) for x, y in joints]
        for joints in reversed(LEGS[pose])
    ]
    left, right = run_through(solid[crotch - 2], round(middle))
    left, right = max(left, middle - 0.09 * tall), min(right, middle + 0.09 * tall)
    low = crotch + 0.07 * tall

    def seat(grow: float) -> list[tuple[float, float]]:
        top = crotch - 2
        return [(left - grow, top), (right + grow, top), (middle + width / 2 + grow, low)] + [
            (middle - width / 2 - grow, low)
        ]

    for colour, grow in ((INK, 3), (appearance.bottom_colour, 0)):
        for path in paths:
            draw.line(path, fill=colour, width=width + 2 * grow, joint="curve")
        draw.polygon(seat(grow), colour)
    for path in paths:
        x, y = path[-1]
        draw.rounded_rectangle(
            (x - width / 2, y, x - width / 2 + foot, y + sole),
            radius=width // 3,
            fill=appearance.shoe_colour,
            outline=INK,
            width=3,
        )
    if any(a.value == "apron" for a in appearance.accessories):
        keep = apron(painting, solid, round(middle), top + round(APRON * tall))
        pixels = np.asarray(out).copy()
        pixels[keep] = np.asarray(painting.convert("RGB"))[keep]
        out = Image.fromarray(pixels)
    return out


def apron(painting: Image.Image, solid: NDArray[np.bool_], x: int, y: int) -> NDArray[np.bool_]:
    """The apron hanging over the legs, with its outline: the patch painted like it at (x, y)."""
    from simile.dolls.colour import cielab, delta_e_lab

    lab = cielab(np.asarray(painting.convert("RGB"), dtype=np.float64))
    patch = touching(solid & (delta_e_lab(lab, lab[y, x]) < APRON_NEAR), x, y)
    grown = Image.fromarray(patch.astype(np.uint8) * 255).filter(
        ImageFilter.MaxFilter(2 * APRON_EDGE + 1)
    )
    return (np.asarray(grown) > 0) & solid


def touching(mask: NDArray[np.bool_], x: int, y: int) -> NDArray[np.bool_]:
    """The pixels of `mask` joined to (x, y), corners included."""
    patch = np.zeros_like(mask)
    if not mask[y, x]:
        return patch
    patch[y, x] = True
    todo = [(y, x)]
    height, width = mask.shape
    while todo:
        cy, cx = todo.pop()
        for ny in range(max(0, cy - 1), min(height, cy + 2)):
            for nx in range(max(0, cx - 1), min(width, cx + 2)):
                if mask[ny, nx] and not patch[ny, nx]:
                    patch[ny, nx] = True
                    todo.append((ny, nx))
    return patch


def run_through(row: NDArray[np.bool_], x: int) -> tuple[int, int]:
    """The stretch of opaque pixels in `row` that `x` is in, or just `x`."""
    if not row[x]:
        return x, x
    left = x - int(np.argmin(row[x::-1])) + 1 if not row[: x + 1].all() else 0
    right = x + int(np.argmin(row[x:])) - 1 if not row[x:].all() else len(row) - 1
    return left, right


def crotch_row(solid: NDArray[np.bool_], top: int, bottom: int) -> int:
    """Where the legs part: the highest row below the hands split in two, or three-quarters of
    the way down."""
    tall = bottom - top
    for y in range(top + round(0.68 * tall), bottom):
        row = np.concatenate([[False], solid[y], [False]]).astype(np.int8)
        if len(np.flatnonzero(np.diff(row))) >= 4:
            return y
    return top + round(0.75 * tall)
