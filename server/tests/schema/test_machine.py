import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from simile.schema import MODELS, Item, Machine, MachineKind, MachineState, Material, export

MACHINES: list[dict[str, Any]] = json.loads((Path(__file__).parent / "machines.json").read_text())
BROKEN, PRINTER, RECYCLER, UNOFFERING = MACHINES


@pytest.mark.parametrize("data", MACHINES, ids=["broken", "printer", "recycler", "unoffering"])
def test_fixture_round_trips_and_the_schema_accepts_it(data: dict[str, Any]) -> None:
    parsed = Machine.model_validate_json(json.dumps(data))

    assert json.loads(parsed.model_dump_json()) == data
    Draft202012Validator(json.loads((export.JSON_DIR / "Machine.json").read_text())).validate(data)


def test_it_is_exported() -> None:
    assert Machine in MODELS


def test_a_broken_machine_lists_what_a_repair_uses_up() -> None:
    machine = Machine.model_validate(BROKEN)

    assert machine.kind is MachineKind.PRINTER
    assert machine.state is MachineState.BROKEN
    assert machine.parts == {"metal_sheet": 1, "linear_actuator": 1, "copper_wire": 2}
    assert machine.makes == []


def test_a_product_is_a_whole_item_priced_in_what_it_uses() -> None:
    pistol, rounds = Machine.model_validate(PRINTER).makes

    assert isinstance(pistol.item, Item)
    assert (pistol.uses, pistol.cost) == (Material.PLASTIC, 6)
    assert pistol.item.rounds == 0
    assert (rounds.uses, rounds.cost, rounds.item.amount) == (Material.PLASTIC, 2, 6)


def test_the_recycler_makes_material_from_scrap_by_the_kilo() -> None:
    plastic = Machine.model_validate(RECYCLER).makes[0]

    assert (plastic.uses, plastic.cost, plastic.item.amount) == ("scrap", 1, 1)
    assert plastic.item.material is Material.PLASTIC


def test_a_machine_can_work_before_it_makes_anything() -> None:
    assert Machine.model_validate(UNOFFERING).makes == []


@pytest.mark.parametrize(
    ("update", "match"),
    [
        (BROKEN | {"state": "working"}, "a working machine needs no parts"),
        (BROKEN | {"parts": {}}, "a broken machine needs parts"),
        (PRINTER | {"state": "broken", "parts": BROKEN["parts"]}, "makes nothing"),
        (PRINTER | {"parts": {"copper_wire": 2}}, "a working machine needs no parts"),
        (PRINTER | {"makes": [PRINTER["makes"][0]] * 2}, "each item once"),
        (BROKEN | {"parts": {"copper_wire": 0}}, "greater than or equal to 1"),
        (BROKEN | {"kind": "loom"}, "Input should be"),
        (BROKEN | {"state": "dusty"}, "Input should be"),
        (BROKEN | {"id": "Printer 3D"}, "should match pattern"),
        (PRINTER | {"makes": [PRINTER["makes"][0] | {"uses": "carbon"}]}, "Input should be"),
        (PRINTER | {"makes": [PRINTER["makes"][0] | {"cost": 0}]}, "greater than 0"),
    ],
)
def test_rejects_invalid_machines(update: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        Machine.model_validate(update)
