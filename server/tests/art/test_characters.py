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
    MIRRORED,
    PLAYER,
    POSE_COLUMNS,
    POSES,
    SAMPLES,
    SKIN_TONES,
    STANDING,
    THREE_QUARTER,
    TOP_DOWN,
    Colours,
    atlas,
    draw_frame,
    draw_pose,
    full_sheet,
    pose_frames,
    pose_name,
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
    drawn = {"down", "left", "up", "down_left", "up_left"}
    for style in HAIR.values():
        assert set(style) == drawn
    for art in ACCESSORY_ART.values():
        assert set(art) == drawn


@pytest.mark.parametrize(("hair_style", "build"), list(itertools.product(HairStyle, Build)))
def test_every_hair_style_and_build_renders(hair_style: HairStyle, build: Build) -> None:
    assert_well_formed(look(hair_style=hair_style, build=build, accessories=[]))


@pytest.mark.parametrize("accessory", list(Accessory))
def test_every_accessory_renders(accessory: Accessory) -> None:
    for hair_style in HairStyle:
        assert_well_formed(look(hair_style=hair_style, accessories=[accessory]))


def test_all_accessories_together_render() -> None:
    assert_well_formed(look(hair_style="curly", accessories=list(Accessory)))


def test_sheet_is_a_3_by_8_grid_of_16_by_24_frames() -> None:
    sheet = sprite_sheet(PLAYER)
    assert (sheet.width, sheet.height) == (48, 192)
    assert DIRECTIONS[:4] == TOP_DOWN == ("down", "left", "right", "up")
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


@pytest.mark.parametrize(("right", "left"), MIRRORED.items())
def test_right_facings_mirror_left_ones(right: str, left: str) -> None:
    for frame in range(FRAMES):
        mirror = draw_frame(PLAYER, left, frame).flipped()
        assert draw_frame(PLAYER, right, frame).pixels == mirror.pixels


@pytest.mark.parametrize(
    ("quarter", "between"), [("down_left", ("down", "left")), ("up_left", ("up", "left"))]
)
def test_three_quarter_views_are_drawn_on_their_own(quarter: str, between: tuple[str, str]) -> None:
    for appearance in [PLAYER, *SAMPLES.values()]:
        for frame in range(FRAMES):
            view = draw_frame(appearance, quarter, frame).pixels
            assert all(view != draw_frame(appearance, d, frame).pixels for d in between)


def test_three_quarter_views_stand_where_the_others_do() -> None:
    def extent(c: Canvas) -> tuple[int, int]:
        rows = [y for y in range(FRAME_HEIGHT) if any(c.get(x, y) for x in range(FRAME_WIDTH))]
        return rows[0], rows[-1]

    for appearance in [PLAYER, *SAMPLES.values()]:
        for frame in range(FRAMES):
            front = extent(draw_frame(appearance, "down", frame))
            for direction in THREE_QUARTER:
                top, feet = extent(draw_frame(appearance, direction, frame))
                assert feet == front[1] == FRAME_HEIGHT - 1, direction
                assert abs(top - front[0]) <= 1, direction


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
    width = 16 * (FRAMES + POSE_COLUMNS)
    assert data["meta"]["image"] == "mei.png"
    assert data["meta"]["size"] == {"w": width, "h": 192}
    walk = {f"{d}-{c}" for d in DIRECTIONS for c in range(FRAMES)}
    still = {pose_name(*frame) for frame in pose_frames()}
    assert set(data["frames"]) == walk | still
    cells = set()
    for name, frame in data["frames"].items():
        rect = frame["frame"]
        if name in walk:
            direction, col = name.split("-")
            y = DIRECTIONS.index(direction) * 24
            assert rect == {"x": int(col) * 16, "y": y, "w": 16, "h": 24}
        assert rect["x"] + 16 <= width and rect["y"] + 24 <= 192
        assert frame["sourceSize"] == {"w": 16, "h": 24}
        assert not frame["rotated"] and not frame["trimmed"]
        cells.add((rect["x"], rect["y"]))
    assert len(cells) == len(data["frames"]) == 24 + 8 + 4 * 2 * 4


def test_the_full_sheet_is_the_walk_then_each_still_frame_where_the_atlas_says() -> None:
    sheet = full_sheet(PLAYER)
    frames = atlas("player.png")["frames"]
    walk = sprite_sheet(PLAYER)

    def at(name: str) -> list[list[str | None]]:
        rect = frames[name]["frame"]
        rows = sheet.pixels[rect["y"] : rect["y"] + 24]
        return [row[rect["x"] : rect["x"] + 16] for row in rows]

    assert [row[:48] for row in sheet.pixels] == walk.pixels
    for direction, pose, shift in pose_frames():
        drawn = draw_pose(PLAYER, direction, pose, shift).pixels
        assert at(pose_name(direction, pose, shift)) == drawn


@pytest.mark.parametrize("pose", POSES)
def test_each_pose_is_drawn_for_every_three_quarter_direction(pose: str) -> None:
    for appearance in [PLAYER, *SAMPLES.values()]:
        for direction in THREE_QUARTER:
            still = draw_frame(appearance, direction, 1).pixels
            posed = draw_pose(appearance, direction, pose)
            assert posed.pixels != still, (pose, direction)
            assert draw_pose(appearance, direction, pose, shift=True).pixels != posed.pixels
            feet = max(y for y in range(FRAME_HEIGHT) for x in range(16) if posed.get(x, y))
            assert feet == FRAME_HEIGHT - 1, (pose, direction)
    for right, left in MIRRORED.items():
        if right in THREE_QUARTER:
            mirror = draw_pose(PLAYER, left, pose).flipped()
            assert draw_pose(PLAYER, right, pose).pixels == mirror.pixels


def test_the_poses_differ_from_each_other() -> None:
    for direction in THREE_QUARTER:
        drawn = {tuple(map(tuple, draw_pose(PLAYER, direction, p).pixels)) for p in POSES}
        assert len(drawn) == len(POSES), direction


def test_standing_shifts_its_weight_in_every_direction() -> None:
    for direction in DIRECTIONS:
        still = draw_frame(PLAYER, direction, 1)
        assert draw_pose(PLAYER, direction, STANDING).pixels == still.pixels
        assert draw_pose(PLAYER, direction, STANDING, shift=True).pixels != still.pixels


@pytest.mark.parametrize(("hair_style", "build"), list(itertools.product(HairStyle, Build)))
def test_every_look_poses_cleanly(hair_style: HairStyle, build: Build) -> None:
    for accessories in ([], list(Accessory)):
        appearance = look(hair_style=hair_style, build=build, accessories=accessories)
        for direction, pose, shift in pose_frames():
            c = draw_pose(appearance, direction, pose, shift)
            assert c.colours() <= set(PALETTE)
            for x, y in itertools.product(range(FRAME_WIDTH), range(FRAME_HEIGHT)):
                if x in (0, FRAME_WIDTH - 1) or y in (0, FRAME_HEIGHT - 1):
                    assert c.get(x, y) in (None, "ink"), (direction, pose, shift, x, y)


def test_samples_and_f2_fixture_npcs_render() -> None:
    npcs = [Npc.model_validate_json(p.read_text()) for p in sorted(FIXTURES.glob("*.json"))]
    assert npcs
    for appearance in [PLAYER, *SAMPLES.values(), *(npc.appearance for npc in npcs)]:
        assert_well_formed(appearance)
    assert len({tuple(map(tuple, sprite_sheet(a).pixels)) for a in SAMPLES.values()}) == 10
