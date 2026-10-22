import json
from pathlib import Path
from typing import Any

from simile.schema import Item, ItemKind
from simile.street.village import GROUND, village
from simile.world.map import (
    PICKUPS_LAYER,
    SOLID_LAYER,
    STREET_DIR,
    Pickup,
    PickupKind,
    TownMap,
    load_map,
    load_maps,
)

MAPS = load_maps(STREET_DIR)


def test_reads_every_solid_cell_the_street_builder_made() -> None:
    for plan in village():
        town = MAPS[plan.id]
        found = {(x, y) for y in range(town.height) for x in range(town.width) if town.solid(x, y)}
        assert found == plan.solid, plan.id


def test_ground_ledges_and_walls_are_solid_and_off_the_map_is_too() -> None:
    lane, room = MAPS["lychee_lane"], MAPS["house_1_floor_0"]

    assert lane.solid(10, GROUND + 1) and not lane.solid(10, GROUND)
    assert lane.solid(46, GROUND - 2) and not lane.solid(46, GROUND - 3)
    assert room.solid(0, 1) and room.solid(3, 3) and not room.solid(3, 2)
    assert lane.solid(-1, GROUND) and lane.solid(10, -1) and lane.solid(lane.width, GROUND)


def test_without_a_solid_layer_anywhere_nobody_can_walk_is_solid(tmp_path: Path) -> None:
    data = json.loads((STREET_DIR / "kapok_walk.tmj").read_text())
    data["layers"] = [layer for layer in data["layers"] if layer["name"] != SOLID_LAYER]
    (tmp_path / "kapok_walk.tmj").write_text(json.dumps(data))

    town = load_map(tmp_path / "kapok_walk.tmj")

    assert town.solids == ()
    assert town.solid(10, 5) and town.solid(10, GROUND + 1) and not town.solid(10, GROUND)
    plain = TownMap("plain", 2, 1, ((False, True),), ())
    assert not plain.solid(0, 0) and plain.solid(1, 0)


def pickup(object_id: int, name: str, kind: str, x: int, y: int, **props: Any) -> dict[str, Any]:
    kinds = {float: "float", str: "string"}
    return {
        "id": object_id,
        "name": name,
        "type": kind,
        "x": x * 16,
        "y": y * 16,
        "width": 16,
        "height": 16,
        "rotation": 0,
        "visible": True,
        "properties": [
            {"name": key, "type": kinds[type(value)], "value": value}
            for key, value in sorted(props.items())
        ],
    }


def test_reads_salvage_and_secrets_from_the_pickups_layer(tmp_path: Path) -> None:
    data = json.loads((STREET_DIR / "kapok_walk.tmj").read_text())
    objects = [
        pickup(901, "metro_salvage_1", "salvage", 38, GROUND - 3),
        pickup(902, "metro_secret_stairwell", "secret", 8, GROUND - 8, money=25.0),
        pickup(
            903,
            "metro_secret_alcove",
            "secret",
            86,
            GROUND - 7,
            item="ration_pack",
            item_kind="food",
            item_name="Ration pack",
            item_weight=0.5,
        ),
    ]
    data["layers"].append({"name": PICKUPS_LAYER, "type": "objectgroup", "objects": objects})
    (tmp_path / "kapok_walk.tmj").write_text(json.dumps(data))

    town = load_map(tmp_path / "kapok_walk.tmj")

    ration = Item(id="ration_pack", kind=ItemKind.FOOD, name="Ration pack", weight=0.5)
    assert town.pickups == (
        Pickup("metro_salvage_1", PickupKind.SALVAGE, "kapok_walk", 38, GROUND - 3),
        Pickup("metro_secret_stairwell", PickupKind.SECRET, "kapok_walk", 8, GROUND - 8, 25.0),
        Pickup("metro_secret_alcove", PickupKind.SECRET, "kapok_walk", 86, GROUND - 7, item=ration),
    )


def test_a_map_without_a_pickups_layer_has_none() -> None:
    assert MAPS["kapok_walk"].pickups == ()
