import json
from pathlib import Path

import pytest

from simile.protocol import Wall
from simile.schema import Tile
from simile.world.map import MAP_DIR, MuralWall, TownMap, load_map, load_maps, with_every_location


@pytest.fixture(scope="module")
def maps() -> dict[str, TownMap]:
    return load_maps()


def buildings(street: str) -> list[dict]:
    data = json.loads((MAP_DIR / f"{street}.tmj").read_text())
    [layer] = [layer for layer in data["layers"] if layer["name"] == "buildings"]
    size = data["tilewidth"]
    return [
        {
            "id": o["name"],
            "x0": o["x"] // size,
            "x1": (o["x"] + o["width"]) // size,
            **{p["name"]: p["value"] for p in o["properties"]},
        }
        for o in layer["objects"]
    ]


def building_of(wall: MuralWall) -> dict:
    assert wall.map is not None
    [building] = [b for b in buildings(wall.map) if b["x0"] <= wall.x < b["x1"]]
    return building


def test_there_are_four_to_six_walls_on_different_buildings(maps: dict[str, TownMap]) -> None:
    walls = with_every_location(maps).murals
    ids = [wall.id for wall in walls]

    assert 4 <= len(ids) <= 6
    assert len(set(ids)) == len(ids) == len({building_of(wall)["id"] for wall in walls})
    for wall in walls:
        sent = Wall(
            id=wall.id,
            x=wall.x,
            y=wall.y,
            width=wall.width,
            face=wall.face,
            bottom=wall.bottom,
            top=wall.top,
            mural=None,
            map=wall.map,
        )
        assert sent.map == wall.map


def test_every_wall_faces_the_camera_on_a_street_front(maps: dict[str, TownMap]) -> None:
    for town in maps.values():
        for wall in town.murals:
            b = building_of(wall)
            assert town.street and wall.map == town.id, wall.id
            assert wall.face == "south" and wall.width >= 3, wall.id
            assert b["x0"] <= wall.x and wall.x + wall.width <= b["x1"], wall.id
            assert 0 < wall.bottom < wall.top <= b["storeys"], wall.id


def test_every_painter_stands_on_the_street_in_front_of_their_wall(
    maps: dict[str, TownMap],
) -> None:
    for town in maps.values():
        for wall in town.murals:
            stand = wall.stand
            assert town.standing(stand.x, stand.y), wall.id
            assert stand.y == wall.y and wall.x <= stand.x < wall.x + wall.width, wall.id


def test_load_map_reads_mural_walls_in_tiles_on_their_map(tmp_path: Path) -> None:
    def wall(name: str, face: str, x: int, y: int, width: int, height: int) -> dict:
        props = {"bottom": 0.5, "face": face, "stand_x": 1, "stand_y": 2, "top": 1.5}
        return {
            "name": name,
            "type": "mural_wall",
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "properties": [{"name": k, "value": v} for k, v in props.items()],
        }

    layers = [
        {"name": "collision", "type": "tilelayer", "data": [0] * 12},
        {"name": "locations", "type": "objectgroup", "objects": []},
        {
            "name": "murals",
            "type": "objectgroup",
            "objects": [wall("long", "south", 0, 16, 48, 16), wall("high", "south", 32, 0, 16, 16)],
        },
    ]
    path = tmp_path / "tiny.tmj"
    path.write_text(json.dumps({"width": 4, "height": 3, "tilewidth": 16, "layers": layers}))

    tiny = load_map(path)

    stand = Tile(x=1, y=2)
    assert tiny.murals == (
        MuralWall("long", 0, 1, 3, "south", 0.5, 1.5, stand, "tiny"),
        MuralWall("high", 2, 0, 1, "south", 0.5, 1.5, stand, "tiny"),
    )
    assert tiny.mural("high") is tiny.murals[1]
    with pytest.raises(KeyError):
        tiny.mural("nowhere")
