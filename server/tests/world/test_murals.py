import json
import math
from pathlib import Path

import pytest

from simile.art.iso.camera import TILE_H, UPRIGHT_PX_PER_M
from simile.art.iso.town import STOREY_M, Building
from simile.art.iso.town import Town as IsoTown
from simile.protocol import Wall
from simile.schema import Tile
from simile.world.build_map import facade
from simile.world.map import MAP_PATH, MuralWall, TownMap, load_map

BLANK = {name for m in ("cream", "slate") for row in facade(m, "...", "...") for name in row}
BLANK |= {"cafe_wall_l", "cafe_wall", "cafe_wall_r"}
CLIMB_PER_TILE = TILE_H / UPRIGHT_PX_PER_M


@pytest.fixture(scope="module")
def town() -> TownMap:
    return load_map()


@pytest.fixture(scope="module")
def iso() -> IsoTown:
    return IsoTown(MAP_PATH)


def building_of(iso: IsoTown, wall: MuralWall) -> Building:
    [building] = [b for b in iso.buildings if b.x0 <= wall.x < b.x1 and b.y0 <= wall.y < b.y1]
    return building


def face_points(wall: MuralWall) -> list[tuple[float, float, float]]:
    points = []
    for i in range(wall.width * 4):
        along = (i + 0.5) / 4
        for j in range(8):
            z = (wall.bottom + (wall.top - wall.bottom) * (j + 0.5) / 8) * STOREY_M
            if wall.face == "south":
                points.append((wall.x + along, wall.y + 1, z))
            else:
                points.append((wall.x + 1, wall.y + along, z))
    return points


def sight_line_hits(point: tuple[float, float, float], box: tuple[float, ...]) -> bool:
    """Whether the line from a point toward the iso camera passes through a box on the map."""
    x, y, z = point
    x0, y0, x1, y1, z0, z1 = box
    near = max(x0 - x, y0 - y, (z0 - z) / CLIMB_PER_TILE, 0.0)
    far = min(x1 - x, y1 - y, (z1 - z) / CLIMB_PER_TILE)
    return near < far


def test_there_are_four_to_six_walls_on_different_buildings(town: TownMap, iso: IsoTown) -> None:
    ids = [wall.id for wall in town.murals]
    buildings = {building_of(iso, wall).id for wall in town.murals}

    assert 4 <= len(ids) <= 6
    assert len(set(ids)) == len(ids) == len(buildings)
    for wall in town.murals:
        Wall(
            id=wall.id,
            x=wall.x,
            y=wall.y,
            width=wall.width,
            face=wall.face,
            bottom=wall.bottom,
            top=wall.top,
            mural=None,
        )


def test_every_wall_is_blank_facade_on_a_face_the_camera_sees(town: TownMap, iso: IsoTown) -> None:
    for wall in town.murals:
        b = building_of(iso, wall)
        assert wall.width >= 3, wall.id
        assert 0 < wall.bottom < wall.top <= b.storeys, wall.id
        if wall.face == "east":
            assert wall.x == b.x1 - 1 and wall.y + wall.width <= b.y1, wall.id
            continue
        # The renders draw windows, doors and signs on south faces only.
        assert wall.y == b.y1 - 1 and wall.x + wall.width <= b.x1, wall.id
        for storey in range(math.floor(wall.bottom), math.ceil(wall.top)):
            row = b.facade[b.storeys - 1 - storey]
            for tile, decor in row[wall.x - b.x0 : wall.x - b.x0 + wall.width]:
                assert tile in BLANK and decor is None, (wall.id, storey, tile, decor)


def test_nothing_stands_between_a_wall_and_the_iso_camera(town: TownMap, iso: IsoTown) -> None:
    boxes = {b.id: (*b.footprint, 0.0, b.height_m) for b in iso.buildings}
    for prop in iso.props:
        x0, y0, x1, y1 = prop.footprint
        r = prop.reach * math.sqrt(0.5)
        boxes[prop.id] = (x0 - r, y0 - r, x1 + r, y1 + r, 0.0, prop.height_m)

    for wall in town.murals:
        hidden_by = {
            name
            for point in face_points(wall)
            for name, box in boxes.items()
            if sight_line_hits(point, box)
        }
        assert not hidden_by, wall.id


def test_every_painter_stands_on_a_walkable_tile_in_front_of_their_wall(town: TownMap) -> None:
    for wall in town.murals:
        stand = wall.stand
        assert town.walkable(stand.x, stand.y), wall.id
        if wall.face == "south":
            assert stand.y == wall.y + 1 and wall.x <= stand.x < wall.x + wall.width, wall.id
        else:
            assert stand.x == wall.x + 1 and wall.y <= stand.y < wall.y + wall.width, wall.id


def test_load_map_reads_mural_walls_in_tiles(tmp_path: Path) -> None:
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
            "objects": [wall("long", "south", 0, 16, 48, 16), wall("tall", "east", 32, 0, 16, 32)],
        },
    ]
    path = tmp_path / "tiny.tmj"
    path.write_text(json.dumps({"width": 4, "height": 3, "tilewidth": 16, "layers": layers}))

    tiny = load_map(path)

    stand = Tile(x=1, y=2)
    assert tiny.murals == (
        MuralWall("long", 0, 1, 3, "south", 0.5, 1.5, stand),
        MuralWall("tall", 2, 0, 2, "east", 0.5, 1.5, stand),
    )
    assert tiny.mural("tall") is tiny.murals[1]
    with pytest.raises(KeyError):
        tiny.mural("nowhere")
