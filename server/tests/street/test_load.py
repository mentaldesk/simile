import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from simile.schema import DoorKind, Location, LocationKind, MapArea, Tile, TileArea
from simile.world.map import (
    INTERIORS,
    MAP_DIR,
    MAP_ID,
    MapKind,
    TownMap,
    load_map,
    load_maps,
    with_every_location,
)
from simile.world.movement import Point, inside

SIZE = 16


def prop(name: str, value: Any) -> dict[str, Any]:
    kinds = {bool: "bool", int: "int", str: "string"}
    return {"name": name, "type": kinds[type(value)], "value": value}


def rectangle(name: str, type_: str, x: int, width: int, props: dict[str, Any]) -> dict:
    """An object on a map's one row."""
    return {
        "name": name,
        "type": type_,
        "x": x * SIZE,
        "y": 0,
        "width": width * SIZE,
        "height": SIZE,
        "properties": [prop(k, v) for k, v in sorted(props.items())],
    }


def link(name: str, x: int, side: str, to_map: str, to_x: int, kind: str | None = None) -> dict:
    props = {"side": side, "to_map": to_map, "to_x": to_x, "to_y": 0}
    return rectangle(name, "door", x, 1, props | ({"kind": kind} if kind else {}))


def side_view_map(
    width: int,
    kind: str,
    doors: list[dict] | None = None,
    locations: list[dict] | None = None,
    climbable: list[int] | None = None,
    **props: Any,
) -> dict[str, Any]:
    """One row to stand on over a row of ground."""
    layers = [
        {"name": "collision", "type": "tilelayer", "data": [0] * width + [1] * width},
        {"name": "doors", "type": "objectgroup", "objects": doors or []},
        {"name": "locations", "type": "objectgroup", "objects": locations or []},
    ]
    if climbable is not None:
        layers.append({"name": "climbable", "type": "tilelayer", "data": climbable})
    names = ["blocked", "solid", "stairs", "ladder"]
    tiles = [{"id": i, "properties": [prop("name", name)]} for i, name in enumerate(names)]
    props = {"view": "side", "kind": kind, **props}
    return {
        "width": width,
        "height": 2,
        "tilewidth": SIZE,
        "layers": layers,
        "properties": [prop(k, v) for k, v in sorted(props.items())],
        "tilesets": [{"firstgid": 1, "tiles": tiles}],
    }


def write(folder: Path, map_id: str, data: dict[str, Any]) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{map_id}.tmj"
    path.write_text(json.dumps(data))
    return path


def house() -> Location:
    return Location(
        id="house_1",
        name="1 High Street",
        kind=LocationKind.HOUSE,
        map="house_1_floor_0",
        area=TileArea(x=0, y=0, width=6, height=1),
        entry=Tile(x=2, y=0),
        floors=[MapArea(map="house_1_floor_1", x=0, y=0, width=6, height=1)],
    )


def village(
    tmp_path: Path,
    streets: tuple[str, str] = ("high_street", "mill_lane"),
    stairs: tuple[int, int] = (0, 1),
    floors: str = "house_1_floor_1:0,0,6,1",
) -> Path:
    """Two streets joined by a door, the first's at its outside end, and a house on the first
    with two floors and stairs between them, the first's at its outside end."""
    first, second = streets
    to_second = link("streets", 5, "outside", second, 0)
    front_door = link("house_1", 2, "outside", "house_1_floor_0", 1)
    write(tmp_path, first, side_view_map(6, "street", doors=[to_second, front_door]))
    to_first = link("streets", 0, "inside", first, 5)
    write(tmp_path, second, side_view_map(6, "street", doors=[to_first]))
    low, high = stairs
    flight = {
        low: link("house_1_stairs", 4, "outside", f"house_1_floor_{high}", 4, "stairs"),
        high: link("house_1_stairs", 4, "inside", f"house_1_floor_{low}", 4, "stairs"),
    }
    props = {"entry_x": 2, "entry_y": 0, "label": "1 High Street"}
    location = rectangle("house_1", "house", 0, 6, props | ({"floors": floors} if floors else {}))
    for floor, doors, locations in (
        (0, [flight[0], link("house_1", 1, "inside", first, 2)], [location]),
        (1, [flight[1]], []),
    ):
        data = side_view_map(6, "floor", doors, locations, building="house_1", floor=floor)
        write(tmp_path / "floors", f"house_1_floor_{floor}", data)
    return tmp_path


def test_reads_the_kind_of_each_link_and_the_floors_of_a_location(tmp_path: Path) -> None:
    maps = load_maps(village(tmp_path))
    ground = maps["house_1_floor_0"]
    doors = {door.id: door for door in ground.doors}

    assert doors["house_1_stairs"].kind is DoorKind.STAIRS
    assert doors["house_1"].kind is DoorKind.DOOR
    assert ground.location("house_1") == house()
    assert list(maps) == ["high_street", "mill_lane", "house_1_floor_0", "house_1_floor_1"]


def test_reads_whether_a_map_is_a_side_view_street_or_floor_and_its_building(
    tmp_path: Path,
) -> None:
    maps = load_maps(village(tmp_path))
    street, floor = maps["high_street"], maps["house_1_floor_1"]

    assert (street.side_view, street.kind, street.building, street.floor) == (
        True,
        MapKind.STREET,
        None,
        None,
    )
    assert (floor.side_view, floor.kind, floor.building, floor.floor) == (
        True,
        MapKind.FLOOR,
        "house_1",
        1,
    )
    assert street.climbable == ()
    assert street.climb(0, 0) is None


def test_reads_climbable_cells_by_their_marker_names(tmp_path: Path) -> None:
    data = side_view_map(4, "street", climbable=[0, 3, 4, 0, 0, 0, 0, 0])
    town = load_map(write(tmp_path, "high_street", data))

    assert town.climbable[0] == (None, DoorKind.STAIRS, DoorKind.LADDER, None)
    assert [town.standing(x, 0) for x in range(4)] == [True, False, False, True]


def test_a_door_object_without_a_kind_is_a_door(tmp_path: Path) -> None:
    data = side_view_map(4, "street", doors=[link("shop", 1, "outside", "shop_floor_0", 1)])
    [door] = load_map(write(tmp_path, "high_street", data)).doors

    assert door.kind is DoorKind.DOOR
    assert "kind" not in door.model_fields_set


def test_rejects_a_map_where_two_links_share_an_end_tile(tmp_path: Path) -> None:
    doors = [link("shop", 1, "outside", "shop_floor_0", 1), link("cafe", 1, "outside", "cafe", 1)]
    path = write(tmp_path, "high_street", side_view_map(4, "street", doors=doors))

    with pytest.raises(ValueError, match="share an end tile"):
        load_map(path)


def test_rejects_maps_where_two_links_share_an_end_tile_on_another_map(tmp_path: Path) -> None:
    village(tmp_path)
    mill = json.loads((tmp_path / "mill_lane.tmj").read_text())
    mill["layers"][1]["objects"].append(link("ford", 3, "inside", "high_street", 5))
    (tmp_path / "mill_lane.tmj").write_text(json.dumps(mill))

    with pytest.raises(ValueError, match="share an end tile"):
        load_maps(tmp_path)


@pytest.mark.parametrize(
    ("streets", "ok"),
    [(("high_street", "mill_lane"), True), (("mill_lane", "high_street"), False)],
    ids=["outside first", "outside second"],
)
def test_two_streets_join_through_a_door_outside_on_the_street_whose_id_comes_first(
    tmp_path: Path, streets: tuple[str, str], ok: bool
) -> None:
    village(tmp_path, streets=streets)

    if ok:
        [door] = [d for d in load_maps(tmp_path)["high_street"].doors if d.id == "streets"]
        assert (door.kind, door.outside.map, door.inside.map) == (
            DoorKind.DOOR,
            "high_street",
            "mill_lane",
        )
    else:
        with pytest.raises(ValueError, match="street whose id comes first"):
            load_maps(tmp_path)


def test_rejects_stairs_whose_outside_is_the_upper_floor(tmp_path: Path) -> None:
    village(tmp_path, stairs=(1, 0))

    with pytest.raises(ValueError, match="joins? a floor of a building to one above it"):
        load_maps(tmp_path)


def test_rejects_a_floor_its_building_doesnt_list(tmp_path: Path) -> None:
    village(tmp_path, floors="")

    with pytest.raises(ValueError, match="isn't one of house_1's floors"):
        load_maps(tmp_path)


def test_rejects_a_link_to_a_map_that_isnt_there(tmp_path: Path) -> None:
    village(tmp_path)
    (tmp_path / "floors" / "house_1_floor_1.tmj").unlink()

    with pytest.raises(ValueError, match="isn't there"):
        load_maps(tmp_path)


def test_a_directory_without_maps_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_maps(tmp_path)


def todays_load_maps(directory: Path) -> dict[str, TownMap]:
    """`load_maps` as it was before side-view maps, which reads today's maps the same."""
    from simile.world.map import (
        COLLISION_LAYER,
        DOORS_LAYER,
        INTERACTABLES_LAYER,
        LOCATIONS_LAYER,
        MURALS_LAYER,
        SPOTS_LAYER,
        _door,
        _interactable,
        _location,
        _mural,
        _spot,
    )

    def read(path: Path) -> TownMap:
        data = json.loads(path.read_text())
        map_id, width, height, size = path.stem, data["width"], data["height"], data["tilewidth"]
        layers = {layer["name"]: layer for layer in data["layers"]}
        cells = layers[COLLISION_LAYER]["data"]
        blocked = tuple(
            tuple(gid != 0 for gid in cells[y * width : (y + 1) * width]) for y in range(height)
        )

        def objects(layer: str) -> list[dict[str, Any]]:
            return layers.get(layer, {}).get("objects", [])

        return TownMap(
            map_id,
            width,
            height,
            blocked,
            locations=tuple(_location(o, size, map_id) for o in objects(LOCATIONS_LAYER)),
            murals=tuple(_mural(o, size) for o in objects(MURALS_LAYER)),
            doors=tuple(_door(o, size, map_id) for o in objects(DOORS_LAYER)),
            interactables=tuple(
                _interactable(o, size, map_id) for o in objects(INTERACTABLES_LAYER)
            ),
            spots=tuple(_spot(o, size, map_id) for o in objects(SPOTS_LAYER)),
        )

    paths = [directory / f"{MAP_ID}.tmj", *sorted((directory / INTERIORS).glob("*.tmj"))]
    return {town.id: town for town in map(read, paths)}


def test_todays_maps_load_exactly_as_before() -> None:
    maps, before = load_maps(), todays_load_maps(MAP_DIR)

    assert list(maps) == list(before)
    for map_id, town in maps.items():
        assert town == before[map_id], map_id
        assert not town.side_view and town.kind is None and town.climbable == ()
        for door, old in zip(town.doors, before[map_id].doors, strict=True):
            assert door.model_fields_set == old.model_fields_set
        for location, old in zip(town.locations, before[map_id].locations, strict=True):
            assert location.model_fields_set == old.model_fields_set


def test_every_location_on_todays_maps_is_the_village_as_before() -> None:
    maps = load_maps()
    village_map = maps[MAP_ID]
    found: dict[str, Location] = {}
    for town in (village_map, *maps.values()):
        for location in town.locations:
            found.setdefault(location.id, location)

    assert with_every_location(maps) == replace(village_map, locations=tuple(found.values()))


def test_every_location_without_a_village_is_on_the_first_street(tmp_path: Path) -> None:
    maps = load_maps(village(tmp_path))
    town = with_every_location(maps)

    assert town.id == "high_street"
    assert town.location("house_1") == house()
    assert {door.id for door in town.doors} == {"streets", "house_1", "house_1_stairs"}
    assert with_every_location({"house_1_floor_1": maps["house_1_floor_1"]}).id == (
        "house_1_floor_1"
    )


def test_a_location_takes_in_its_floors() -> None:
    location = house()

    assert inside(location, Point(2, 0, "house_1_floor_0"))
    assert inside(location, Point(5, 0, "house_1_floor_1"))
    assert inside(location, (5, 0))
    assert not inside(location, Point(6, 0, "house_1_floor_1"))
    assert not inside(location, Point(2, 0, "house_2_floor_1"))
    assert not inside(location, Point(2, 0, "high_street"))


def test_rejects_a_door_between_a_street_and_an_upper_floor(tmp_path: Path) -> None:
    village(tmp_path)
    street = json.loads((tmp_path / "high_street.tmj").read_text())
    street["layers"][1]["objects"].append(link("roof", 0, "outside", "house_1_floor_1", 0))
    (tmp_path / "high_street.tmj").write_text(json.dumps(street))
    floor = json.loads((tmp_path / "floors" / "house_1_floor_1.tmj").read_text())
    floor["layers"][1]["objects"].append(link("roof", 0, "inside", "high_street", 0))
    (tmp_path / "floors" / "house_1_floor_1.tmj").write_text(json.dumps(floor))

    with pytest.raises(ValueError, match="a street and a ground floor"):
        load_maps(tmp_path)
