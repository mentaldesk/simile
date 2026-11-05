import inspect
import json

import numpy as np
import pytest
from PIL import Image

from simile.papercraft.build import CONTENT, MANIFEST
from simile.papercraft.catalogue import EXTRAS, FURNITURE, PLATFORMS
from simile.papercraft.fronts import GREY
from simile.papercraft.sketches import SKETCHES

PIECES = json.loads((CONTENT / MANIFEST).read_text())["pieces"]
SEATED = ("bed", "stool", "bench", "cafe_table", "noodle_table", "table", "picture_frame")
STRETCH_CAP = 0.15
"""The share of a stretched piece's width the client keeps at each end."""
SEAT_X = {"bench": 0.74, "cafe_table": 0.22, "table": 0.22, "noodle_table": 0.2}
"""Metres from each sketch's left edge to the middle of a seat."""


def drawn(name: str) -> np.ndarray:
    a = np.asarray(SKETCHES[name](), dtype=np.int16)
    return np.abs(a - a[0, 0]).max(axis=2) > 6


def covers(name: str, x: float, y: float) -> bool:
    """Whether the sketch draws anything `x`, `y` metres from its bottom left."""
    shape = drawn(name)
    rows, cols = np.flatnonzero(shape.any(axis=1)), np.flatnonzero(shape.any(axis=0))
    ppm = (rows[-1] - rows[0] + 1) / {**FURNITURE, **EXTRAS, **PLATFORMS}[name].height
    return bool(shape[round(rows[-1] - y * ppm), round(cols[0] + x * ppm)])


@pytest.mark.parametrize("name", SEATED)
def test_a_seat_sketch_keeps_todays_proportions(name: str) -> None:
    shape = drawn(name)
    rows, cols = np.flatnonzero(shape.any(axis=1)), np.flatnonzero(shape.any(axis=0))
    size = PIECES[f"furniture/{name}"]["size"]

    assert (cols[-1] - cols[0] + 1) / (rows[-1] - rows[0] + 1) == pytest.approx(
        size[0] / size[1], rel=0.06
    )


def drawn_at(name: str, parameter: str) -> float:
    return inspect.signature(SKETCHES[name]).parameters[parameter].default


@pytest.mark.parametrize("name", sorted(SEAT_X))
def test_a_seat_sketch_puts_its_seat_near_where_its_art_has_it(name: str) -> None:
    seat = drawn_at(name, "seat")

    assert covers(name, SEAT_X[name], seat - 0.02)
    assert not covers(name, SEAT_X[name], seat + 0.03)
    assert FURNITURE[name].seat == pytest.approx(seat, abs=0.07)


def test_the_bed_has_its_headboard_on_the_left_and_its_mattress_near_its_arts() -> None:
    mattress = drawn_at("bed", "mattress")

    assert covers("bed", 0.05, 1.0) and not covers("bed", 1.4, 1.0)
    assert covers("bed", 1.2, mattress - 0.02) and not covers("bed", 1.2, mattress + 0.03)
    assert FURNITURE["bed"].bed == pytest.approx(mattress, abs=0.07)


@pytest.mark.parametrize(
    "name", ("bed", "cafe_table", "noodle_table", "picture_frame", "kitchen", "window", "fridge")
)
def test_a_pale_sketch_is_drawn_on_grey(name: str) -> None:
    assert SKETCHES[name]().getpixel((0, 0)) == GREY


def test_the_kitchen_keeps_its_sink_and_hob_in_the_ends_a_stretch_keeps() -> None:
    shape = drawn("kitchen")
    rows, cols = np.flatnonzero(shape.any(axis=1)), np.flatnonzero(shape.any(axis=0))
    ppm = (rows[-1] - rows[0] + 1) / FURNITURE["kitchen"].height
    above = shape[rows[0] : rows[-1] - round(0.86 * ppm), cols[0] : cols[-1] + 1]
    end = round(above.shape[1] * STRETCH_CAP)

    assert above[:, :end].any() and above[:, -end:].any()
    assert not above[:, end:-end].any()


def test_the_window_is_as_wide_as_todays() -> None:
    shape = drawn("window")
    rows, cols = np.flatnonzero(shape.any(axis=1)), np.flatnonzero(shape.any(axis=0))
    ppm = (rows[-1] - rows[0] + 1) / PLATFORMS["window"].height

    assert (cols[-1] - cols[0] + 1) / ppm == pytest.approx(1.48, abs=0.02)


def test_the_painted_kitchen_has_nothing_above_its_worktop_where_a_stretch_repeats() -> None:
    entry = PIECES["furniture/kitchen"]
    alpha = np.asarray(Image.open(CONTENT / entry["file"]).getchannel("A")) > 128
    width = alpha.shape[1]
    worktop = np.flatnonzero(alpha.sum(axis=1) > 0.8 * width)[0]
    end = round(width * STRETCH_CAP)

    assert not alpha[: worktop - 1, end : width - end].any()
