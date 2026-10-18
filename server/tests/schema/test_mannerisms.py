import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from simile.characters.pool import character_files, save
from simile.npc.content import NPCS_DIR, load_npcs, readme_seed, write_npcs
from simile.schema import Character, Npc, export

type Kind = type[Npc] | type[Character]
type Case = tuple[Kind, dict[str, Any]]

HERE = Path(__file__).parent
WITHOUT: list[tuple[Kind, Path]] = [
    (Npc, HERE.parent / "fixtures" / "npcs" / "viktor.json"),
    (Character, HERE / "characters" / "premade.json"),
]

MANNERISMS = ["answers a question with another question", "trails off when a story turns sad"]


def data(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def schema(model: Kind) -> Draft202012Validator:
    return Draft202012Validator(data(export.JSON_DIR / f"{model.__name__}.json"))


@pytest.fixture(params=WITHOUT, ids=lambda case: case[0].__name__)
def case(request: pytest.FixtureRequest) -> Case:
    model, path = request.param
    return model, data(path)


def test_without_mannerisms_they_are_empty_and_left_out(case: Case) -> None:
    model, item = case
    parsed = model.model_validate(item)

    assert parsed.mannerisms == []
    assert "mannerisms" not in json.loads(parsed.model_dump_json())
    assert "mannerisms" not in parsed.model_dump()


def test_mannerisms_round_trip_after_the_speaking_style(case: Case) -> None:
    model, item = case
    parsed = model.model_validate(item | {"mannerisms": MANNERISMS})

    dumped = json.loads(parsed.model_dump_json())
    keys = list(dumped)

    assert dumped["mannerisms"] == MANNERISMS
    assert keys[keys.index("speaking_style") + 1] == "mannerisms"
    assert model.model_validate_json(parsed.model_dump_json()) == parsed


def test_up_to_three_mannerisms_of_120_characters_fit(case: Case) -> None:
    model, item = case
    longest = ["x" * 120] * 3

    assert model.model_validate(item | {"mannerisms": longest}).mannerisms == longest


@pytest.mark.parametrize(
    ("mannerisms", "match"),
    [
        (MANNERISMS * 2, "at most 3 items"),
        ([""], "at least 1 character"),
        (["x" * 121], "at most 120 characters"),
        ("answers a question with another question", "valid list"),
    ],
)
def test_mannerisms_are_few_and_short(case: Case, mannerisms: Any, match: str) -> None:
    model, item = case

    with pytest.raises(ValidationError, match=match):
        model.model_validate(item | {"mannerisms": mannerisms})


def test_the_exported_schema_allows_but_does_not_require_mannerisms(case: Case) -> None:
    model, item = case

    assert schema(model).is_valid(item)
    assert schema(model).is_valid(item | {"mannerisms": MANNERISMS})
    assert not schema(model).is_valid(item | {"mannerisms": MANNERISMS * 2})
    assert not schema(model).is_valid(item | {"mannerisms": [""]})
    assert not schema(model).is_valid(item | {"mannerisms": ["x" * 121]})


def test_the_committed_residents_rewrite_byte_for_byte(tmp_path: Path) -> None:
    paths = sorted(NPCS_DIR.glob("*.json"))
    assert paths

    write_npcs(load_npcs(NPCS_DIR), tmp_path, readme_seed())

    for path in paths:
        assert (tmp_path / path.name).read_bytes() == path.read_bytes(), path.name


def test_the_committed_pool_rewrites_byte_for_byte(tmp_path: Path) -> None:
    paths = character_files()
    assert paths

    for path in paths:
        written = save(Character.model_validate_json(path.read_bytes()), tmp_path)
        assert written.read_bytes() == path.read_bytes(), path.name
