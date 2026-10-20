import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from simile.schema import Door, DoorKind, Location, MapArea, Model, export

from .conftest import DOOR

FIXTURES = Path(__file__).parents[1] / "fixtures"

HOUSE: dict[str, Any] = json.loads((FIXTURES / "locations.json").read_text())[0]
FLOORS = [
    {"map": "house_1_floor_1", "x": 1, "y": 2, "width": 8, "height": 4},
    {"map": "house_1_floor_2", "x": 1, "y": 2, "width": 6, "height": 4},
]
STAIRS = {
    "id": "house_1_stairs",
    "kind": "stairs",
    "outside": {"map": "house_1", "x": 7, "y": 9},
    "inside": {"map": "house_1_floor_1", "x": 7, "y": 5},
}


def schema(model: type[Model]) -> Draft202012Validator:
    path = export.JSON_DIR / f"{model.__name__}.json"
    return Draft202012Validator(json.loads(path.read_text()))


def rejects(model: type[Model], data: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        model.model_validate(data)


def test_a_door_without_a_kind_is_a_door_and_dumps_without_one() -> None:
    door = Door.model_validate(DOOR)

    assert door.kind is DoorKind.DOOR
    assert "kind" not in json.loads(door.model_dump_json())
    assert "kind" not in door.model_dump()


def test_a_door_given_the_door_kind_still_dumps_without_one() -> None:
    assert json.loads(Door.model_validate(DOOR | {"kind": "door"}).model_dump_json()) == DOOR


@pytest.mark.parametrize("kind", ["stairs", "ladder", "lift"])
def test_stairs_ladders_and_lifts_round_trip_after_the_id(kind: str) -> None:
    door = Door.model_validate(STAIRS | {"kind": kind})
    dumped = json.loads(door.model_dump_json())

    assert door.kind is DoorKind(kind)
    assert dumped == STAIRS | {"kind": kind}
    assert list(dumped) == ["id", "kind", "outside", "inside"]
    assert Door.model_validate_json(door.model_dump_json()) == door


def test_a_door_kind_is_door_stairs_ladder_or_lift() -> None:
    assert [kind.value for kind in DoorKind] == ["door", "stairs", "ladder", "lift"]
    rejects(Door, STAIRS | {"kind": "escalator"}, "kind")


@pytest.mark.parametrize("kind", ["door", "stairs", "ladder", "lift"])
def test_every_kind_still_links_two_maps(kind: str) -> None:
    inside = STAIRS["inside"] | {"map": "house_1"}

    rejects(Door, STAIRS | {"kind": kind, "inside": inside}, "a door links two different maps")


def test_a_location_without_floors_has_none_and_dumps_without_them() -> None:
    location = Location.model_validate(HOUSE)

    assert location.floors == []
    assert json.loads(location.model_dump_json()) == HOUSE
    assert "floors" not in location.model_dump()


def test_floors_round_trip_after_the_entry() -> None:
    location = Location.model_validate(HOUSE | {"map": "house_1", "floors": FLOORS})
    dumped = json.loads(location.model_dump_json())
    keys = list(dumped)

    assert location.floors == [MapArea.model_validate(floor) for floor in FLOORS]
    assert dumped["floors"] == FLOORS
    assert keys[keys.index("entry") + 1] == "floors"
    assert Location.model_validate_json(location.model_dump_json()) == location


@pytest.mark.parametrize(
    "floors",
    [
        [FLOORS[0] | {"map": "house_1"}],
        [FLOORS[0], FLOORS[1] | {"map": FLOORS[0]["map"]}],
    ],
    ids=["on its own map", "two on one map"],
)
def test_each_floor_is_on_a_map_of_its_own(floors: list[dict[str, Any]]) -> None:
    rejects(Location, HOUSE | {"map": "house_1", "floors": floors}, "a map of its own")


@pytest.mark.parametrize(
    ("update", "match"),
    [
        ({"map": ""}, "at least 1 character"),
        ({"x": -1}, "floors.0.x"),
        ({"width": 0}, "floors.0.width"),
        ({"height": 0}, "floors.0.height"),
        ({"storey": 1}, "Extra inputs are not permitted"),
    ],
)
def test_floor_fields_follow_the_rules(update: dict[str, Any], match: str) -> None:
    rejects(Location, HOUSE | {"map": "house_1", "floors": [FLOORS[0] | update]}, match)


def test_the_exported_door_takes_but_does_not_require_a_kind() -> None:
    assert schema(Door).is_valid(DOOR)
    assert schema(Door).is_valid(STAIRS)
    assert not schema(Door).is_valid(STAIRS | {"kind": "escalator"})


def test_the_exported_location_takes_but_does_not_require_floors() -> None:
    assert schema(Location).is_valid(HOUSE)
    assert schema(Location).is_valid(HOUSE | {"map": "house_1", "floors": FLOORS})
    assert not schema(Location).is_valid(HOUSE | {"floors": [FLOORS[0] | {"width": 0}]})
