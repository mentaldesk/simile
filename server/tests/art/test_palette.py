import re

from simile.art.palette import PALETTE, RGB, SHADE, nearest, shade


def test_palette_has_32_distinct_hex_colours() -> None:
    assert len(PALETTE) == 32
    assert len(set(PALETTE.values())) == 32
    assert all(re.fullmatch(r"#[0-9a-f]{6}", value) for value in PALETTE.values())


def test_every_colour_has_a_darker_or_equal_shade_in_the_palette() -> None:
    assert set(SHADE) == set(PALETTE)
    for name, darker in SHADE.items():
        assert darker in PALETTE
        assert sum(RGB[darker]) <= sum(RGB[name])


def test_shade_steps_through_the_ramp() -> None:
    assert shade("white", 2) == "concrete"


def test_palette_colours_snap_to_themselves() -> None:
    for name, rgb in RGB.items():
        assert nearest(rgb) == name


def test_snapping_is_perceptual() -> None:
    assert nearest((0xD9, 0x64, 0x5A)) == "pink"
