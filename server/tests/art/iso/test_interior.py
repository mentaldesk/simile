import json
from pathlib import Path

import pytest

from simile.art.iso import camera
from simile.art.iso.interior import (
    CUT_M,
    FITTING_SHAPE,
    FLOOR_DECOR,
    PAIRS,
    PARTITION_M,
    RUNS,
    SINGLES,
    WALL_DECOR,
    WALL_M,
    Interior,
    find,
)
from simile.art.iso.lighting import INSIDE
from simile.art.iso.scenery import CONTENT_DIR

ROOMS = {room.id: room for room in find(CONTENT_DIR)}


def tmj(room: Interior) -> dict:
    return json.loads((CONTENT_DIR / "map" / "interiors" / f"{room.id}.tmj").read_text())


def objects(room: Interior, layer: str) -> list[dict]:
    return next(lay for lay in tmj(room)["layers"] if lay["name"] == layer)["objects"]


def collides(room: Interior) -> set[str]:
    tileset = tmj(room)["tilesets"][0]
    out = set()
    for tile in tileset["tiles"]:
        props = {p["name"]: p["value"] for p in tile.get("properties", [])}
        if props.get("collides"):
            out.add(props["name"])
    return out


def test_there_are_the_four_interiors() -> None:
    assert sorted(ROOMS) == ["coffee_shop", "gallery", "maker_space", "noodle_bar"]


@pytest.mark.parametrize("room", ROOMS.values(), ids=list(ROOMS))
def test_the_floor_is_the_rooms_own_location(room: Interior) -> None:
    own = next(o for o in objects(room, "locations") if o["name"] == room.id)
    area = (
        o // 16 for o in (own["x"], own["y"], own["x"] + own["width"], own["y"] + own["height"])
    )
    assert (room.fx0, room.fy0, room.fx1, room.fy1) == tuple(area)


@pytest.mark.parametrize("room", ROOMS.values(), ids=list(ROOMS))
def test_every_tile_inside_is_drawn_by_something(room: Interior) -> None:
    known = {*FLOOR_DECOR, *SINGLES, "frame_l", "frame_r"}
    known |= {name for names in RUNS.values() for name in names}
    known |= {f"{base}_{end}" for base in (*PAIRS, *WALL_DECOR) for end in ("l", "r")}
    known |= set(WALL_DECOR)
    for row in room.layers["decor"]:
        assert {name for name in row if name} <= known
    for row in room.layers["buildings"]:
        assert all(name.startswith("inwall_") for name in row if name)


@pytest.mark.parametrize("room", ROOMS.values(), ids=list(ROOMS))
def test_everything_in_the_way_on_the_floor_is_a_fitting(room: Interior) -> None:
    covered = {(x, y) for f in room.fittings for x, y, _ in f.model["cells"]}
    blocking = collides(room)
    for y, row in enumerate(room.layers["decor"]):
        for x, name in enumerate(row):
            if name in blocking:
                assert (x, y) in covered, (name, x, y)


@pytest.mark.parametrize("room", ROOMS.values(), ids=list(ROOMS))
def test_the_north_and_west_walls_stand_full_height_and_the_others_are_cut_away(
    room: Interior,
) -> None:
    walls = {w.id: w for w in room.walls}
    assert walls["wall-north"].height_m == walls["wall-west"].height_m == WALL_M
    assert walls["wall-east"].height_m == CUT_M
    south = [w for w in room.walls if w.id.startswith("wall-south")]
    assert south and all(w.height_m == CUT_M for w in south)
    assert walls["wall-north"].footprint[3] == room.fy0
    assert walls["wall-west"].footprint[2] == room.fx0
    assert walls["wall-east"].footprint[0] == room.fx1
    assert all(w.footprint[1] == room.fy1 for w in south)


@pytest.mark.parametrize("room", ROOMS.values(), ids=list(ROOMS))
def test_the_door_is_a_gap_in_the_south_wall(room: Interior) -> None:
    doors = [(d["x"] // 16, d["y"] // 16) for d in objects(room, "doors")]
    [(mx, my)] = room.mats()
    assert my == room.fy1
    assert doors in ([], [(mx, my)])
    south = [w.footprint for w in room.walls if w.id.startswith("wall-south")]
    assert not any(x0 < mx + 1 and mx < x1 for x0, _, x1, _ in south)
    assert room.ground()[my][mx] != "void"


@pytest.mark.parametrize("room", ROOMS.values(), ids=list(ROOMS))
def test_only_the_floor_and_the_doorway_have_ground(room: Interior) -> None:
    ground = room.ground()
    for y in range(room.height):
        for x in range(room.width):
            inside = room.fx0 <= x < room.fx1 and room.fy0 <= y < room.fy1
            assert (ground[y][x] != "void") == (inside or (x, y) in room.mats()), (x, y)


def test_the_gallerys_partitions_are_free_standing_walls() -> None:
    gallery = ROOMS["gallery"]
    partitions = [w for w in gallery.walls if w.model["face"] == "partition"]
    assert [w.footprint for w in partitions] == [(4, 10.75, 14, 11), (18, 10.75, 28, 11)]
    assert all(w.height_m == PARTITION_M for w in partitions)
    assert gallery.open_ground == partitions


def test_every_painting_has_an_empty_frame_on_its_wall() -> None:
    gallery = ROOMS["gallery"]
    paintings = {o["name"]: o for o in objects(gallery, "interactables")}
    frames = {f.id: f for f in gallery.frames}
    assert sorted(frames) == sorted(paintings)
    for pid, painting in paintings.items():
        frame = frames[pid]
        x0, _, x1, _ = frame.footprint
        px = painting["x"] / 16
        assert px < x0 < x1 < px + painting["width"] / 16
        props = {p["name"]: p["value"] for p in painting["properties"]}
        stand_y = int(props["stand"].split()[0].split(",")[1])
        assert frame.model["face_y"] == stand_y
        assert frame.model["face_y"] in (gallery.fy0, 11)


def test_a_frames_canvas_is_inside_it_and_upright() -> None:
    frame = ROOMS["gallery"].frames[0]
    top_left, top_right, bottom_right, bottom_left = frame.canvas()
    x0, y0, x1, _ = frame.footprint
    assert x0 < top_left[0] < top_right[0] < x1
    assert top_left[1] == top_right[1] == bottom_right[1] == bottom_left[1] == y0
    assert top_left[2] == top_right[2] > bottom_right[2] == bottom_left[2]
    assert camera.project(*top_left)[1] < camera.project(*bottom_left)[1]
    assert frame.spec()["kind"] == "frame"
    assert ROOMS["gallery"].walls[0].canvas() is None


def test_counters_against_the_wall_and_in_front_of_it_are_apart() -> None:
    cafe = ROOMS["coffee_shop"]
    kinds = {f.kind for f in cafe.fittings}
    assert {"back_counter", "counter", "cafe_table", "planter", "planter_flowers"} == kinds
    back = next(f for f in cafe.fittings if f.kind == "back_counter")
    front = next(f for f in cafe.fittings if f.kind == "counter")
    assert back.footprint[1] == cafe.fy0
    barista = (5.5, 4.5)
    assert back.footprint[3] < barista[1] < front.footprint[3]


def test_a_fitting_is_flush_to_a_wall_or_its_own_cells_and_inset_elsewhere() -> None:
    cafe = ROOMS["coffee_shop"]
    back = next(f for f in cafe.fittings if f.kind == "back_counter")
    inset = FITTING_SHAPE["back_counter"][0]
    assert back.footprint == (1, 2, 9 - inset, 3 - inset)
    table = next(f for f in cafe.fittings if f.kind == "cafe_table")
    x, y, _ = table.model["cells"][0]
    i = FITTING_SHAPE["cafe_table"][0]
    assert table.footprint == (x + i, y + i, x + 1 - i, y + 1 - i)


def test_a_stool_you_can_stand_on_sorts_behind_whoever_stands_there() -> None:
    stools = [f for f in ROOMS["noodle_bar"].fittings if f.kind == "stool"]
    assert len(stools) == 5
    for stool in stools:
        x0, y0, x1, y1 = stool.footprint
        assert (x0, y0) == (x1, y1) == stool.anchor


def test_pairs_take_two_tiles() -> None:
    maker = ROOMS["maker_space"]
    for f in maker.fittings:
        if f.kind in PAIRS:
            assert len(f.model["cells"]) == 2


@pytest.mark.parametrize("room", ROOMS.values(), ids=list(ROOMS))
def test_ceiling_lights_are_over_the_floor(room: Interior) -> None:
    lights = room.lights()
    assert len(lights) >= 4
    for x, y, _ in lights:
        assert room.fx0 + 1 < x < room.fx1 - 1 and room.fy0 + 1 < y < room.fy1 - 1


@pytest.mark.parametrize("room", ROOMS.values(), ids=list(ROOMS))
def test_ids_are_unique(room: Interior) -> None:
    ids = [o.id for o in room.objects]
    assert len(ids) == len(set(ids))


def test_a_piece_is_rendered_with_what_is_near_it() -> None:
    cafe = ROOMS["coffee_shop"]
    north = next(w for w in cafe.walls if w.id == "wall-north")
    back = next(f for f in cafe.fittings if f.kind == "back_counter")
    far = next(f for f in cafe.fittings if f.id == "cafe_table-2-11")
    context = cafe.context(back, INSIDE)
    assert north in context and back not in context and far not in context


def test_an_interior_with_no_partitions_reads_from_any_map(tmp_path: Path) -> None:
    data = tmj(ROOMS["maker_space"])
    path = tmp_path / "workshop.tmj"
    path.write_text(json.dumps(data))
    room = Interior(path)
    assert room.id == "workshop"
    assert room.finish == "block" and room.floor == "floor_concrete"
    assert room.open_ground == []
