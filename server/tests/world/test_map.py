import json
import shutil
from collections import Counter, deque
from pathlib import Path

import pytest
from PIL import Image
from pydantic import TypeAdapter
from typer.testing import CliRunner

from simile.cli import create_cli
from simile.schema import Location, LocationKind
from simile.world.build_map import Tileset, Town
from simile.world.map import CONTENT_DIR, MAP_PATH, WALKING_SPEED, TownMap, load_map

ART = CONTENT_DIR / "art"


@pytest.fixture(scope="module")
def town() -> TownMap:
    return load_map()


def distances(town: TownMap, start: tuple[int, int]) -> dict[tuple[int, int], int]:
    found = {start: 0}
    queue = deque([start])
    while queue:
        x, y = queue.popleft()
        for step in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if town.walkable(*step) and step not in found:
                found[step] = found[x, y] + 1
                queue.append(step)
    return found


def test_every_required_location_exists(town: TownMap) -> None:
    ids = [location.id for location in town.locations]
    kinds = Counter(location.kind for location in town.locations)

    assert len(ids) == len(set(ids))
    assert {f"house_{n}" for n in range(1, 11)} | {"coffee_shop", "square"} <= set(ids)
    assert kinds[LocationKind.HOUSE] == 10
    assert kinds[LocationKind.COFFEE_SHOP] == kinds[LocationKind.SQUARE] == 1
    assert 2 <= kinds[LocationKind.TERMINAL] <= 3
    assert 2 <= kinds[LocationKind.AMENITY] <= 3


def test_every_entry_is_reachable_from_the_square(town: TownMap) -> None:
    square = town.location("square").entry
    reachable = distances(town, (square.x, square.y))

    for location in town.locations:
        entry, area = location.entry, location.area
        assert (entry.x, entry.y) in reachable, location.id
        assert area.x <= entry.x < area.x + area.width, location.id
        assert area.y <= entry.y < area.y + area.height, location.id


def test_no_walkable_tile_is_cut_off(town: TownMap) -> None:
    square = town.location("square").entry
    walkable = {
        (x, y) for y in range(town.height) for x in range(town.width) if town.walkable(x, y)
    }

    assert walkable == set(distances(town, (square.x, square.y)))


def test_the_farthest_two_places_are_about_a_minute_apart(town: TownMap) -> None:
    entries = [(location.entry.x, location.entry.y) for location in town.locations]
    longest = max(max(distances(town, a)[b] for b in entries) for a in entries)

    assert 40 <= longest / WALKING_SPEED <= 80


def test_f2_location_fixtures_stand_where_the_map_puts_them(town: TownMap) -> None:
    fixtures = Path(__file__).parents[1] / "fixtures" / "locations.json"
    locations = TypeAdapter(list[Location]).validate_json(fixtures.read_bytes())

    for location in locations:
        expected = town.location(location.id).model_copy(update={"name": location.name})
        assert location == expected, location.id


def test_walkable(town: TownMap) -> None:
    cafe = town.location("coffee_shop").entry

    assert len(town.blocked) == town.height
    assert {len(row) for row in town.blocked} == {town.width}
    assert town.walkable(cafe.x, cafe.y)
    assert not town.walkable(cafe.x, cafe.y - 1)
    for x, y in ((-1, 0), (0, -1), (town.width, 0), (0, town.height)):
        assert not town.walkable(x, y)
    with pytest.raises(KeyError):
        town.location("nowhere")


def test_load_map_reads_locations_in_tiles(tmp_path: Path) -> None:
    obj = {
        "name": "noodle_bar",
        "type": "amenity",
        "x": 16,
        "y": 32,
        "width": 48,
        "height": 16,
        "properties": [
            {"name": "entry_x", "type": "int", "value": 2},
            {"name": "entry_y", "type": "int", "value": 2},
            {"name": "label", "type": "string", "value": "Noodles"},
        ],
    }
    layers = [
        {"name": "collision", "type": "tilelayer", "data": [0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0]},
        {"name": "locations", "type": "objectgroup", "objects": [obj]},
    ]
    path = tmp_path / "tiny.tmj"
    path.write_text(json.dumps({"width": 4, "height": 3, "tilewidth": 16, "layers": layers}))

    tiny = load_map(path)

    assert (tiny.id, tiny.width, tiny.height) == ("tiny", 4, 3)
    assert [x for x in range(4) if not tiny.walkable(x, 1)] == [3]
    [location] = tiny.locations
    assert location.name == "Noodles" and location.kind == LocationKind.AMENITY
    assert location.area.model_dump() == {"x": 1, "y": 2, "width": 3, "height": 1}
    assert location.entry.model_dump() == {"x": 2, "y": 2}
    assert tiny.murals == ()


def test_the_map_is_a_tiled_map_with_the_tileset_embedded() -> None:
    data = json.loads(MAP_PATH.read_text())
    standalone = json.loads((ART / "tiles.tsj").read_text())
    [tileset] = data["tilesets"]

    assert (data["type"], data["orientation"], data["infinite"]) == ("map", "orthogonal", False)
    assert data["tilewidth"] == data["tileheight"] == 16
    assert tileset["firstgid"] == 1 and "source" not in tileset
    assert (MAP_PATH.parent / tileset["image"]).resolve() == (ART / standalone["image"]).resolve()
    assert {k: v for k, v in tileset.items() if k not in ("firstgid", "image")} == {
        k: v for k, v in standalone.items() if k not in ("type", "version", "tiledversion", "image")
    }
    names = ["ground", "buildings", "decor", "above", "collision", "locations", "murals"]
    assert [layer["name"] for layer in data["layers"]] == names


def test_the_collision_layer_marks_every_tile_that_collides() -> None:
    data = json.loads(MAP_PATH.read_text())
    props = {
        tile["id"] + 1: {p["name"]: p["value"] for p in tile["properties"]}
        for tile in data["tilesets"][0]["tiles"]
    }
    layers = {layer["name"]: layer["data"] for layer in data["layers"] if "data" in layer}
    size = data["width"] * data["height"]

    for name, cells in layers.items():
        assert len(cells) == size, name
        assert all(gid == 0 or gid in props for gid in cells), name
        if name in ("buildings", "decor"):
            assert not any(props[gid]["above"] for gid in cells if gid), name
    assert all(props[gid]["above"] for gid in layers["above"] if gid)
    drawn = [layers[name] for name in ("ground", "buildings", "decor", "above")]
    expected = [any(props[gids[i]]["collides"] for gids in drawn if gids[i]) for i in range(size)]
    assert [gid != 0 for gid in layers["collision"]] == expected


def test_committed_map_is_up_to_date(tmp_path: Path) -> None:
    (tmp_path / "art").mkdir()
    for name in ("tiles.tsj", "tiles.png"):
        shutil.copy(ART / name, tmp_path / "art" / name)

    result = CliRunner().invoke(create_cli(), ["map", "--content", str(tmp_path)])

    assert result.exit_code == 0, result.output
    stale = "content/map is out of date: run `cd server && uv run simile map`"
    fresh, committed = tmp_path / "map", MAP_PATH.parent
    assert {p.name for p in fresh.iterdir()} == {"village.tmj", "preview.png", "locations.png"}
    assert (fresh / "village.tmj").read_text() == (committed / "village.tmj").read_text(), stale
    for name in ("preview.png", "locations.png"):
        with Image.open(fresh / name) as new, Image.open(committed / name) as old:
            assert new.convert("RGBA").tobytes() == old.convert("RGBA").tobytes(), stale


def test_the_builder_rejects_overlaps_and_thin_terrain() -> None:
    town = Town(Tileset.load(ART))
    town.put(1, 1, "bench_l")
    with pytest.raises(ValueError, match="cover bench_l"):
        town.put(1, 1, "bins")

    town.fill("G", 4, 4, 5, 1)
    with pytest.raises(ValueError, match="less than two tiles thick"):
        town.check()
