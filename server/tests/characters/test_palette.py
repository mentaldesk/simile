import re

from simile.characters.palette import (
    PALETTE,
    PLAYER,
    RGB,
    SKIN_TONES,
    accent,
    apron,
    nearest,
    snap,
)
from simile.schema import Appearance


def look(**changes: object) -> Appearance:
    return Appearance.model_validate(PLAYER.model_dump() | changes)


def test_palette_has_32_distinct_hex_colours() -> None:
    assert len(PALETTE) == 32
    assert len(set(PALETTE.values())) == 32
    assert all(re.fullmatch(r"#[0-9a-f]{6}", value) for value in PALETTE.values())


def test_palette_colours_snap_to_themselves() -> None:
    for name, rgb in RGB.items():
        assert nearest(rgb) == name


def test_snapping_is_perceptual() -> None:
    assert nearest((0xD9, 0x64, 0x5A)) == "pink"


def test_skin_and_clothes_snap_to_their_own_colours() -> None:
    assert snap("#2a1a14", SKIN_TONES) in SKIN_TONES
    assert snap("#000000") != "ink"


def test_the_accent_is_never_a_colour_they_wear() -> None:
    dark = look(skin="#2a1a14", top_colour="#000000", hair_colour="#050505")
    worn = {snap(dark.top_colour), snap(dark.bottom_colour), snap(dark.hair_colour)}
    assert accent(dark) not in worn


def test_a_seed_varies_the_accent_but_never_to_an_outfit_colour() -> None:
    cap = look(accessories=["cap"])
    worn = {snap(cap.top_colour), snap(cap.bottom_colour), snap(cap.hair_colour)}
    seeded = [accent(cap, f"npc{i}") for i in range(12)]
    assert len(set(seeded)) > 1
    assert not worn & set(seeded)
    assert accent(cap, "lachlan") != accent(cap, "tobias")


def test_an_apron_stands_out_from_the_top() -> None:
    assert apron(look(top_colour=PALETTE["white"])) == "umber"
    assert apron(look(top_colour=PALETTE["navy"])) == "cream"
