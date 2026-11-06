"""The player aiming the pistol: one painting, with each figure's own parts laid over it."""

import hashlib
import io
import json
from collections.abc import Callable
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from simile.dolls.bionics import (
    COMBINATIONS,
    LOWER,
    REACH,
    Combination,
    figure_id,
    grown,
    laid,
    parts,
    patches,
    regions,
)
from simile.dolls.build import (
    CONTENT,
    GROUND,
    SIZE,
    Cached,
    Cut,
    Painted,
    aim_atlas,
    attempt,
    identify,
    people,
    seed,
    write,
)
from simile.dolls.colour import cielab
from simile.dolls.figure import SAME, Pose, styled
from simile.dolls.sprites import PAD, Frame, cut_out, frames, head, scaled, solid, trimmed
from simile.schema import PLAYER_ID
from simile.schema.player import Bionic

FRAME = "aim"
WORDS = (
    SAME + "standing still and shooting: one arm raised and stretched straight out in front to the "
    "right at shoulder height, the hand gripping a small chunky pistol of bright orange plastic "
    "pointing to the right. The other arm stays relaxed at the side, and the head and the legs "
    "stay exactly as they are. The t-shirt stays blue. The face is clean, with simple dot eyes and "
    "a small smile. Keep the background plain light grey."
)
REROLL = 0
"""A reroll number, for a painting that came out wrong by eye."""
FILL = 0.8
"""How much of the painting's height the standing figure fills."""
HEAD_AT = 0.32
"""Across the painting, where the head goes, to leave room for the arm."""
CANVAS = (320, 200)
FEET = (110, 184)
"""Where every figure's feet go on a canvas big enough for the arm, in atlas pixels."""
LOWER_FROM = 0.72
"""Down the figure, below the hands: a figure with bionic legs or feet is its own from here."""
ARM_FROM = 40
"""Atlas pixels ahead of the feet, past the head and body: only the arm and pistol are here."""
ORANGE = (45.0, 30.0, 35.0)
"""The pistol: lightness, a* and b* above these, CIELAB."""


def prompt() -> str:
    return styled(WORDS)


def fingerprint() -> str:
    """What the aim is painted from: a new one means it's painted again."""
    return hashlib.sha256(f"{prompt()}/{REROLL}".encode()).hexdigest()[:16]


def frame_of(sheet: Image.Image, entry: dict) -> Image.Image:
    x, y, w, h = entry["frame"]
    return sheet.crop((x, y, x + w, y + h))


def on_grey(stand: Image.Image) -> tuple[Image.Image, Image.Image]:
    """The standing frame upscaled, and on FLUX's grey with its head left of the middle."""
    big = scaled(trimmed(stand, 0), FILL * SIZE[1] / trimmed(stand, 0).height)
    painting = Image.new("RGB", SIZE, GROUND)
    x = round(HEAD_AT * SIZE[0] - head(big)[0])
    painting.paste(big, (x, (SIZE[1] - big.height) // 2), big)
    return big, painting


def stood(image: Image.Image, feet: tuple[float, float], up: int = 0) -> Image.Image:
    """A frame on the canvas, its feet at `FEET`, raised `up` pixels."""
    canvas = Image.new("RGBA", CANVAS)
    canvas.paste(image, (round(FEET[0] - feet[0]), round(FEET[1] - feet[1]) - up))
    return canvas


def pistol(figure: Image.Image) -> NDArray[np.bool_]:
    """The biggest patch of bright orange: the red lens of a bionic eye is a much smaller one."""
    lab = cielab(np.asarray(figure.convert("RGB"), dtype=np.float64))
    bright = (lab[..., 0] > ORANGE[0]) & (lab[..., 1] > ORANGE[1]) & (lab[..., 2] > ORANGE[2])
    found = patches(bright & solid(figure))
    return found[0] if found else np.zeros_like(bright)


def unarmed(figure: Image.Image, feet: tuple[float, float]) -> Image.Image:
    """Without the arm and the pistol, whose orange a bionic eye's red is otherwise sought among."""
    out = figure.copy()
    out.paste((0, 0, 0, 0), (round(feet[0]) + ARM_FROM, 0, *figure.size))
    return out


def muzzle(figure: Image.Image) -> tuple[int, int]:
    """The pistol's foremost column, and the middle of what's orange just behind it."""
    found = pistol(figure)
    column = int(np.flatnonzero(found.any(axis=0))[-1])
    behind = found[:, max(0, column - 2) : column + 1]
    return column + 1, int(np.median(np.flatnonzero(behind.any(axis=1))))


def crown(canvas: Image.Image) -> int:
    return int(np.flatnonzero(solid(canvas).any(axis=1))[0])


def near_parts(stand: Image.Image, combination: Combination) -> NDArray[np.bool_]:
    """Round the datajack's light and the eye's lens, where a figure with them shows them."""
    found = parts(stand)
    tall = np.ptp(np.flatnonzero(solid(stand).any(axis=1)))
    where = np.zeros(found[Bionic.DATAJACK].shape, dtype=bool)
    for bionic in set(combination) & set(REACH):
        for patch in patches(found[bionic])[:1]:
            where |= grown(patch, round(REACH[bionic] * tall))
    return where


def fitted_over(
    aimed: Image.Image, stand: Image.Image, feet: tuple[float, float], combination: Combination
) -> Image.Image:
    """`aimed` with what `stand` shows of `combination`, so no trousers show round the parts."""
    if not combination:
        return aimed
    on = stood(stand, feet)
    _, down = regions(on)
    layers = []
    if set(combination) & set(LOWER):
        layers.append((on, down >= LOWER_FROM))
    above = crown(on) - crown(aimed)
    raised = stood(stand, feet, above)
    near = near_parts(raised, combination)
    if near.any():
        layers.append((raised, near))
    return laid(aimed, layers) if layers else aimed


def add_frame(body: dict, aimed: Image.Image) -> bytes:
    """Says in `body` that `aimed` is its aim, and returns the aim's own lossless atlas."""
    box = aimed.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
    box = (max(0, box[0] - PAD), max(0, box[1] - PAD), box[2] + PAD, box[3] + PAD)
    picture = aimed.crop(box)
    body["frames"][FRAME] = {
        "frame": [0, 0, *picture.size],
        "feet": [FEET[0] - box[0], FEET[1] - box[1]],
        "muzzle": list(muzzle(picture)),
        "atlas": aim_atlas(body["id"]),
    }
    body["frames"] = dict(sorted(body["frames"].items()))
    body["poses"][FRAME] = [FRAME]
    body["aimed"] = fingerprint()
    data = io.BytesIO()
    picture.save(data, "WEBP", lossless=True, exact=True, quality=100, method=6)
    return data.getvalue()


def painted_aim(
    painter: Cached, stand: Image.Image, cut: Cut, log: Callable[[str], None]
) -> tuple[Frame, Image.Image]:
    """The aim at the atlas's size, its colours matched as any other pose's, and its painting."""
    appearance = people()[PLAYER_ID]
    big, painting = on_grey(stand)
    found = identify(big, appearance)
    standing = Painted(PLAYER_ID, {n: got for n, (got, _) in found.items()}, {"stand": big})
    number = seed(PLAYER_ID, FRAME, REROLL)
    tried, raw, fixed = attempt(
        painter, prompt(), number, [painting], appearance, cut, Pose(WORDS), standing
    )
    log(f"{FRAME}: scale {tried.scale}, lost {tried.lost}, strays {tried.strays}")
    return frames({"stand": big, FRAME: fixed}, reference=big)[FRAME], raw


def aim(
    painter: Cached,
    directory: Path = CONTENT,
    cut: Cut = cut_out,
    log: Callable[[str], None] = print,
) -> Image.Image:
    """Paints the aim once, adds it to each of the player's figures, and returns the painting."""
    who = json.loads((directory / f"{PLAYER_ID}.json").read_text())
    with Image.open(directory / who["painted"]) as opened:
        stand = frame_of(opened.convert("RGBA"), who["frames"]["stand"])
    made, painting = painted_aim(painter, stand, cut, log)
    aimed = stood(made.image, made.feet)
    for combination in ((), *COMBINATIONS):
        path = directory / f"{figure_id(combination)}.json"
        body = json.loads(path.read_text())
        with Image.open(directory / body["painted"]) as opened:
            sheet = opened.convert("RGBA")
        here = body["frames"]["stand"]
        picture = fitted_over(aimed, frame_of(sheet, here), tuple(here["feet"]), combination)
        data = add_frame(body, picture)
        atlas = body["frames"][FRAME]["atlas"]
        write(directory, {atlas: data, path.name: json.dumps(body, indent=2).encode() + b"\n"})
        log(f"{figure_id(combination)}: aim added")
    return painting
