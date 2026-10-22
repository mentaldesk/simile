import json
from pathlib import Path
from typing import Any

from simile.schema import TileArea
from simile.world.map import Light, load_map


def tiled(path: Path, light: list[dict[str, Any]]) -> Path:
    data = {
        "width": 4,
        "height": 2,
        "tilewidth": 16,
        "tileheight": 16,
        "layers": [
            {"name": "collision", "type": "tilelayer", "data": [0] * 8},
            {"name": "light", "type": "objectgroup", "objects": light},
        ],
    }
    path.write_text(json.dumps(data))
    return path


def area(name: str, x: int, width: int, lit: bool) -> dict[str, Any]:
    props = [{"name": "lit", "type": "bool", "value": lit}]
    return {
        "name": name,
        "x": x * 16,
        "y": 0,
        "width": width * 16,
        "height": 32,
        "properties": props,
    }


def test_a_map_reads_its_lit_and_dark_stretches(tmp_path: Path) -> None:
    light = [area("hall", 0, 1, True), area("tunnel", 1, 3, False)]
    town = load_map(tiled(tmp_path / "metro.tmj", light))

    assert town.light == (
        Light("hall", TileArea(x=0, y=0, width=1, height=2), lit=True),
        Light("tunnel", TileArea(x=1, y=0, width=3, height=2), lit=False),
    )
    assert [town.lit(x, 1) for x in range(4)] == [True, False, False, False]


def test_a_lit_stretch_inside_a_dark_one_is_lit(tmp_path: Path) -> None:
    light = [area("tunnel", 0, 4, False), area("alcove", 2, 1, True)]
    town = load_map(tiled(tmp_path / "metro.tmj", light))

    assert [town.lit(x, 0) for x in range(4)] == [False, False, True, False]


def test_a_map_without_light_is_lit_all_over(tmp_path: Path) -> None:
    town = load_map(tiled(tmp_path / "high_street.tmj", []))

    assert town.light == ()
    assert all(town.lit(x, y) for x in range(4) for y in range(2))
