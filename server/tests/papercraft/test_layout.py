import json
from pathlib import Path
from typing import Any

import pytest

from simile.papercraft.build import CONTENT, MANIFEST
from simile.papercraft.layout import (
    LAYOUT,
    STREET_DIR,
    Facade,
    Mural,
    dumps,
    load_layout,
    loads,
    read_maps,
    refresh,
)


def obj(name: str, type_: str, x: int, y: int, w: int, h: int, **props: Any) -> dict[str, Any]:
    return {
        "name": name,
        "type": type_,
        "x": x * 16,
        "y": y * 16,
        "width": w * 16,
        "height": h * 16,
        "properties": [{"name": k, "value": v} for k, v in props.items()],
    }


def tmj(width: int, props: dict[str, Any], layers: dict[str, list[dict[str, Any]]]) -> str:
    return json.dumps(
        {
            "width": width,
            "height": 4,
            "properties": [{"name": k, "value": v} for k, v in props.items()],
            "tilesets": [
                {"tiles": [{"id": 3, "properties": [{"name": "name", "value": "ladder"}]}]}
            ],
            "layers": [
                {"name": "climbable", "type": "tilelayer", "data": [0] * width * 3 + [4] * width},
                *({"name": n, "type": "objectgroup", "objects": o} for n, o in layers.items()),
            ],
        }
    )


@pytest.fixture
def maps(tmp_path: Path) -> Path:
    (tmp_path / "floors").mkdir()
    (tmp_path / "high_street.tmj").write_text(
        tmj(
            30,
            {"kind": "street", "view": "side"},
            {
                "buildings": [
                    obj("cafe", "building", 2, 5, 9, 11, interior=True, storeys=3, label="Cafe"),
                    obj("tower", "building", 12, 5, 6, 11, interior=False, storeys=3, label="T"),
                ],
                "furniture": [
                    obj("lamp", "lamp", 20, 13, 1, 3),
                    obj("bench", "bench", 22, 15, 2, 1),
                ],
                "doors": [obj("cafe", "door", 8, 15, 1, 1, kind="door", side="outside")],
                "murals": [obj("tower", "mural_wall", 13, 15, 4, 1, bottom=0.15, top=3.0)],
            },
        )
    )
    for floor, room in enumerate(("cafe", "flat")):
        (tmp_path / "floors" / f"cafe_floor_{floor}.tmj").write_text(
            tmj(
                9,
                {"kind": "floor", "building": "cafe", "floor": floor, "room": room},
                {
                    "furniture": [obj("bench", "bench", 1, 2, 3, 1)],
                    "doors": [obj("cafe_stairs", "door", 5, 2, 1, 1, kind="stairs", side="inside")],
                },
            )
        )
    return tmp_path


def test_the_layout_has_each_street_front_floor_and_piece_of_furniture(maps: Path) -> None:
    layout = read_maps(maps)

    assert layout.streets == {"high_street": 30}
    assert layout.facades["cafe"] == Facade("cafe", "high_street", 2, 9, 11, 3, True, door=6)
    assert layout.facades["tower"].murals == (Mural(1, 4, 0.15, 3.0),)
    assert layout.facades["tower"].door is None
    assert layout.rooms == {"cafe": ("cafe", "flat")}
    assert layout.furniture == {"bench": (3, 1), "lamp": (1, 3)}
    assert layout.links == ("ladder", "stairs")


def test_a_layout_survives_its_file(maps: Path) -> None:
    layout = read_maps(maps)

    assert loads(dumps(layout)) == layout


def test_refreshing_writes_only_when_the_maps_change(maps: Path, tmp_path: Path) -> None:
    path = tmp_path / "layout.json"

    assert refresh(maps, path)
    assert not refresh(maps, path)
    assert not refresh(tmp_path / "nowhere", path)


@pytest.mark.skipif(not STREET_DIR.is_dir(), reason="content/street/ isn't there yet")
def test_the_scenery_was_painted_to_the_side_view_maps() -> None:
    assert read_maps(STREET_DIR) == load_layout()


def test_every_street_building_floor_and_piece_of_furniture_on_the_maps_has_its_pieces() -> None:
    layout = read_maps(STREET_DIR) if STREET_DIR.is_dir() else load_layout()
    manifest = json.loads((CONTENT / MANIFEST).read_text())
    pieces = manifest["pieces"]

    for street in layout.streets:
        assert all(key in pieces for key in manifest["streets"][street].values())
    for building, facade in layout.facades.items():
        entry = manifest["buildings"][building]
        assert entry["street"] == facade.street
        assert entry["front"] in pieces and entry["glow"] in pieces
        assert len(entry["floors"]) == len(layout.rooms.get(building, ()))
        assert all(paper in pieces for paper in entry["floors"])
    for name in layout.furniture:
        assert manifest["furniture"][name]["piece"] in pieces
    for link in layout.links:
        assert manifest["platforms"][link] in pieces
    assert LAYOUT.parent == CONTENT
