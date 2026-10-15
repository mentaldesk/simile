import itertools
from pathlib import Path

import pytest

from simile.art.canvas import Canvas
from simile.art.characters import (
    ACCESSORY_ART,
    DIRECTIONS,
    FRAME_HEIGHT,
    FRAME_WIDTH,
    FRAMES,
    FRONT_TORSO,
    HAIR,
    PLAYER,
    SAMPLES,
    SKIN_TONES,
    Colours,
    atlas,
    draw_frame,
    sprite_sheet,
)
from simile.art.palette import PALETTE
from simile.schema import Accessory, Appearance, Build, HairStyle, Npc

FIXTURES = Path(__file__).parents[1] / "fixtures" / "npcs"


def look(**changes: object) -> Appearance:
    return Appearance.model_validate(PLAYER.model_dump() | changes)


def frames(appearance: Appearance) -> list[tuple[str, int, Canvas]]:
    return [
        (direction, frame, draw_frame(appearance, direction, frame))
        for direction in DIRECTIONS
        for frame in range(FRAMES)
    ]


def assert_well_formed(appearance: Appearance) -> None:
    for direction, frame, c in frames(appearance):
        where = (direction, frame)
        assert (c.width, c.height) == (FRAME_WIDTH, FRAME_HEIGHT)
        assert c.colours() <= set(PALETTE), where
        for x, y in itertools.product(range(FRAME_WIDTH), range(FRAME_HEIGHT)):
            on_border = x in (0, FRAME_WIDTH - 1) or y in (0, FRAME_HEIGHT - 1)
            if on_border:
                assert c.get(x, y) in (None, "ink"), f"{where} clips its outline at {x},{y}"


def test_every_schema_option_is_drawn() -> None:
    assert set(HAIR) == {style.value for style in HairStyle}
    assert set(FRONT_TORSO) == {build.value for build in Build}
    assert set(ACCESSORY_ART) == {accessory.value for accessory in Accessory}
    for style in HAIR.values():
        assert set(style) == {"down", "left", "up"}


@pytest.mark.parametrize(("hair_style", "build"), list(itertools.product(HairStyle, Build)))
def test_every_hair_style_and_build_renders(hair_style: HairStyle, build: Build) -> None:
    assert_well_formed(look(hair_style=hair_style, build=build, accessories=[]))


@pytest.mark.parametrize("accessory", list(Accessory))
def test_every_accessory_renders(accessory: Accessory) -> None:
    for hair_style in HairStyle:
        assert_well_formed(look(hair_style=hair_style, accessories=[accessory]))


def test_all_accessories_together_render() -> None:
    assert_well_formed(look(hair_style="curly", accessories=list(Accessory)))


def test_sheet_is_a_3_by_4_grid_of_16_by_24_frames() -> None:
    sheet = sprite_sheet(PLAYER)
    assert (sheet.width, sheet.height) == (48, 96)
    for row, direction in enumerate(DIRECTIONS):
        for col in range(FRAMES):
            frame = draw_frame(PLAYER, direction, col)
            for x, y in itertools.product(range(FRAME_WIDTH), range(FRAME_HEIGHT)):
                assert sheet.get(col * 16 + x, row * 24 + y) == frame.get(x, y)


def test_frames_have_transparent_corners_and_a_visible_character() -> None:
    for _, _, c in frames(PLAYER):
        for x, y in ((0, 0), (15, 0), (0, 23), (15, 23)):
            assert c.get(x, y) is None
        assert sum(c.get(x, y) is not None for x in range(16) for y in range(24)) > 150


def test_right_mirrors_left() -> None:
    for frame in range(FRAMES):
        left = draw_frame(PLAYER, "left", frame)
        assert draw_frame(PLAYER, "right", frame).pixels == left.flipped().pixels


def test_walk_frames_step() -> None:
    for direction in DIRECTIONS:
        step_a, stand, step_b = (draw_frame(PLAYER, direction, f).pixels for f in range(FRAMES))
        assert step_a != stand and step_b != stand and step_a != step_b, direction


@pytest.mark.parametrize(
    "change",
    [
        {"skin": "#733e39"},
        {"hair_colour": "#ff4fa8"},
        {"top_colour": "#63c74d"},
        {"bottom_colour": "#ead4aa"},
        {"shoe_colour": "#e43b44"},
        {"build": "broad"},
        {"hair_style": "bun"},
        {"accessories": ["cap"]},
    ],
)
def test_each_field_changes_the_sprite(change: dict[str, object]) -> None:
    assert sprite_sheet(look(**change)).pixels != sprite_sheet(PLAYER).pixels


def test_colours_snap_to_the_palette() -> None:
    colours = Colours.of(look(skin="#2a1a14", top_colour="#000000", hair_colour="#050505"))
    assert colours.skin in SKIN_TONES
    assert colours.top != "ink"
    assert colours.hair != "ink"
    assert colours.accent not in (colours.top, colours.bottom, colours.hair)


def test_a_seed_varies_the_accent_but_never_to_an_outfit_colour() -> None:
    cap = look(accessories=["cap"])
    seeded = [Colours.of(cap, f"npc{i}") for i in range(12)]
    assert len({c.accent for c in seeded}) > 1
    assert all(c.accent not in (c.top, c.bottom, c.hair) for c in seeded)
    assert Colours.of(cap, "lachlan").accent != Colours.of(cap, "tobias").accent


def test_atlas_is_a_phaser_json_hash_over_the_grid() -> None:
    data = atlas("mei.png")
    assert data["meta"]["image"] == "mei.png"
    assert data["meta"]["size"] == {"w": 48, "h": 96}
    assert set(data["frames"]) == {f"{d}-{c}" for d in DIRECTIONS for c in range(FRAMES)}
    cells = set()
    for name, frame in data["frames"].items():
        direction, col = name.split("-")
        rect = frame["frame"]
        assert rect == {"x": int(col) * 16, "y": DIRECTIONS.index(direction) * 24, "w": 16, "h": 24}
        assert frame["sourceSize"] == {"w": 16, "h": 24}
        assert not frame["rotated"] and not frame["trimmed"]
        cells.add((rect["x"], rect["y"]))
    assert len(cells) == 12


def test_samples_and_f2_fixture_npcs_render() -> None:
    npcs = [Npc.model_validate_json(p.read_text()) for p in sorted(FIXTURES.glob("*.json"))]
    assert npcs
    for appearance in [PLAYER, *SAMPLES.values(), *(npc.appearance for npc in npcs)]:
        assert_well_formed(appearance)
    assert len({tuple(map(tuple, sprite_sheet(a).pixels)) for a in SAMPLES.values()}) == 10
