import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from simile.npc.content import NPCS_DIR
from simile.schema import Character, Humour, HumourStyle, Npc, export

type Kind = type[Npc] | type[Character]
type Case = tuple[Kind, dict[str, Any]]

HERE = Path(__file__).parent
WITHOUT: list[tuple[Kind, Path]] = [
    (Npc, HERE.parent / "fixtures" / "npcs" / "viktor.json"),
    (Character, HERE / "characters" / "premade.json"),
]

DRY = {"style": "dry", "seriousness": 0.7}


def data(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def schema(model: Kind) -> Draft202012Validator:
    return Draft202012Validator(data(export.JSON_DIR / f"{model.__name__}.json"))


@pytest.fixture(params=WITHOUT, ids=lambda case: case[0].__name__)
def case(request: pytest.FixtureRequest) -> Case:
    model, path = request.param
    return model, data(path)


def test_without_a_humour_it_is_none_and_left_out(case: Case) -> None:
    model, item = case
    parsed = model.model_validate(item)

    assert parsed.humour is None
    assert "humour" not in json.loads(parsed.model_dump_json())
    assert "humour" not in parsed.model_dump()


def test_a_humour_round_trips_before_the_interests(case: Case) -> None:
    model, item = case
    parsed = model.model_validate(item | {"humour": DRY, "mannerisms": ["shrugs it off"]})

    dumped = json.loads(parsed.model_dump_json())
    keys = list(dumped)

    assert parsed.humour == Humour(style=HumourStyle.DRY, seriousness=0.7)
    assert dumped["humour"] == DRY
    assert keys[keys.index("mannerisms") + 1] == "humour"
    assert keys[keys.index("humour") + 1] == "interests"
    assert model.model_validate_json(parsed.model_dump_json()) == parsed


@pytest.mark.parametrize("style", list(HumourStyle))
def test_every_style_loads(style: HumourStyle) -> None:
    seriousness = 1 if style is HumourStyle.NONE else 0.5

    assert Humour(style=style, seriousness=seriousness).style is style


@pytest.mark.parametrize(
    ("humour", "match"),
    [
        ({"style": "slapstick", "seriousness": 0.5}, "Input should be"),
        ({"style": "dry", "seriousness": 1.5}, "less than or equal to 1"),
        ({"style": "dry", "seriousness": -0.1}, "greater than or equal to 0"),
        ({"style": "dry"}, "Field required"),
        ({"seriousness": 0.5}, "Field required"),
        ({"style": "none", "seriousness": 0.5}, "seriousness is 1"),
        (DRY | {"often": 0.5}, "Extra inputs"),
    ],
)
def test_a_humour_follows_the_rules(case: Case, humour: dict[str, Any], match: str) -> None:
    model, item = case

    with pytest.raises(ValidationError, match=match):
        model.model_validate(item | {"humour": humour})


def test_the_exported_schema_allows_but_does_not_require_a_humour(case: Case) -> None:
    model, item = case

    assert schema(model).is_valid(item)
    assert schema(model).is_valid(item | {"humour": DRY})
    assert schema(model).is_valid(item | {"humour": {"style": "none", "seriousness": 1}})
    assert not schema(model).is_valid(item | {"humour": {"style": "slapstick", "seriousness": 0}})
    assert not schema(model).is_valid(item | {"humour": {"style": "dry", "seriousness": 2}})
    assert not schema(model).is_valid(item | {"humour": {"style": "dry"}})


def test_every_resident_has_a_humour_and_the_village_keeps_its_range() -> None:
    paths = sorted(NPCS_DIR.glob("*.json"))
    residents = [Npc.model_validate_json(path.read_bytes()) for path in paths]

    for path in paths:
        assert schema(Npc).is_valid(data(path)), path.name
    humours = [npc.humour for npc in residents if npc.humour]
    assert len(humours) == len(residents) == 11
    assert {humour.style for humour in humours} == set(HumourStyle)
    assert sum(humour.seriousness >= 0.9 for humour in humours) >= 3
    assert sum(humour.seriousness < 0.5 for humour in humours) >= 3
