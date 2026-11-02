import json

import numpy as np
import pytest

from simile.papercraft.build import CONTENT, MANIFEST
from simile.papercraft.catalogue import EXTRAS, FURNITURE
from simile.papercraft.sketches import SKETCHES

PIECES = json.loads((CONTENT / MANIFEST).read_text())["pieces"]
SEATED = ("bed", "stool", "bench", "cafe_table", "noodle_table", "table", "picture_frame")
SEAT_X = {"bench": 0.74, "cafe_table": 0.22, "table": 0.22, "noodle_table": 0.2}
"""Metres from each sketch's left edge to the middle of a seat."""


def drawn(name: str) -> np.ndarray:
    a = np.asarray(SKETCHES[name](), dtype=np.int16)
    return np.abs(a - a[0, 0]).max(axis=2) > 6


def covers(name: str, x: float, y: float) -> bool:
    """Whether the sketch draws anything `x`, `y` metres from its bottom left."""
    shape = drawn(name)
    rows, cols = np.flatnonzero(shape.any(axis=1)), np.flatnonzero(shape.any(axis=0))
    ppm = (rows[-1] - rows[0] + 1) / {**FURNITURE, **EXTRAS}[name].height
    return bool(shape[round(rows[-1] - y * ppm), round(cols[0] + x * ppm)])


@pytest.mark.parametrize("name", SEATED)
def test_a_seat_sketch_keeps_todays_proportions(name: str) -> None:
    shape = drawn(name)
    rows, cols = np.flatnonzero(shape.any(axis=1)), np.flatnonzero(shape.any(axis=0))
    size = PIECES[f"furniture/{name}"]["size"]

    assert (cols[-1] - cols[0] + 1) / (rows[-1] - rows[0] + 1) == pytest.approx(
        size[0] / size[1], rel=0.06
    )


@pytest.mark.parametrize("name", sorted(SEAT_X))
def test_a_seat_sketch_puts_its_seat_where_today_does(name: str) -> None:
    seat = FURNITURE[name].seat or FURNITURE["cafe_table"].seat or 0

    assert covers(name, SEAT_X[name], seat - 0.02)
    assert not covers(name, SEAT_X[name], seat + 0.03)


def test_the_bed_has_its_headboard_on_the_left_and_its_mattress_at_todays_height() -> None:
    bed = FURNITURE["bed"].bed or 0

    assert covers("bed", 0.05, 1.0) and not covers("bed", 1.4, 1.0)
    assert covers("bed", 1.2, bed - 0.02) and not covers("bed", 1.2, bed + 0.03)


def test_the_frame_sketch_is_drawn_on_grey_like_its_piece() -> None:
    assert EXTRAS["picture_frame"].grey
    assert SKETCHES["picture_frame"]().getpixel((0, 0)) != (255, 255, 255)
