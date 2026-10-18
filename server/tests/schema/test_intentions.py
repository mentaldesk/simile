import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import TypeAdapter, ValidationError

from simile.behaviour.config import Activity
from simile.schema import (
    MODELS,
    PLAYER_ID,
    Conversation,
    Intention,
    IntentionKind,
    Location,
    Npc,
    export,
)

FIXTURES = Path(__file__).parents[1] / "fixtures"
INTENTIONS: list[dict[str, Any]] = json.loads(
    (Path(__file__).parent / "intentions.json").read_text()
)
CREATE, SEEK, GO, NEWS = INTENTIONS


def load[T](name: str, model: type[T]) -> list[T]:
    return TypeAdapter(list[model]).validate_json((FIXTURES / name).read_bytes())


def schema() -> Draft202012Validator:
    return Draft202012Validator(json.loads((export.JSON_DIR / "Intention.json").read_text()))


def rejects(data: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        Intention.model_validate(data)


@pytest.mark.parametrize("data", INTENTIONS, ids=[i["id"] for i in INTENTIONS])
def test_fixture_round_trips_through_json(data: dict[str, Any]) -> None:
    parsed = Intention.model_validate_json(json.dumps(data))
    dumped = parsed.model_dump_json()

    assert json.loads(dumped) == data
    assert Intention.model_validate_json(dumped) == parsed


def test_a_list_of_them_round_trips_as_the_world_would_save_it() -> None:
    adapter = TypeAdapter(list[Intention])
    parsed = adapter.validate_python(INTENTIONS)

    assert adapter.validate_json(adapter.dump_json(parsed)) == parsed


def test_it_is_exported_and_the_schema_accepts_the_fixtures() -> None:
    assert Intention in MODELS
    for data in INTENTIONS:
        schema().validate(data)

    assert not schema().is_valid(CREATE | {"status": "open"})
    assert not schema().is_valid(CREATE | {"kind": "wander"})


def test_the_fixtures_refer_to_the_fixture_world() -> None:
    npcs = {Npc.model_validate_json(p.read_bytes()).id for p in (FIXTURES / "npcs").glob("*.json")}
    locations = {location.id for location in load("locations.json", Location)}
    participants = {c.id: set(c.participants) for c in load("conversations.json", Conversation)}

    for intention in TypeAdapter(list[Intention]).validate_python(INTENTIONS):
        assert intention.owner in npcs
        assert set(intention.promised_to) <= npcs | {PLAYER_ID}
        if intention.kind is IntentionKind.SEEK:
            assert intention.target in npcs | {PLAYER_ID}
        elif intention.target is not None:
            assert intention.target in locations
        if (conversation := intention.conversation_id) is not None:
            assert {intention.owner, *intention.promised_to} <= participants[conversation]


def test_every_kind_but_go_is_a_b1_activity() -> None:
    assert {kind.value for kind in IntentionKind} - {"go"} <= {a.value for a in Activity}
    assert IntentionKind.GO.value not in {a.value for a in Activity}


def test_due_now_is_due_when_it_was_said() -> None:
    parsed = Intention.model_validate(CREATE)

    assert parsed.due == parsed.created


@pytest.mark.parametrize(
    "data",
    [
        CREATE | {"target": "maker_space"},
        NEWS | {"target": None},
        SEEK | {"target": PLAYER_ID, "promised_to": [PLAYER_ID]},
        GO | {"promised_to": ["mei", PLAYER_ID]},
    ],
)
def test_valid_variations(data: dict[str, Any]) -> None:
    assert Intention.model_validate(data).model_dump(mode="json") == data


def test_timestamps_are_normalised_to_utc() -> None:
    parsed = Intention.model_validate(SEEK | {"due": "2026-03-14T13:30:00+01:00"})

    assert parsed.due == datetime(2026, 3, 14, 12, 30, tzinfo=UTC)
    assert json.loads(parsed.model_dump_json())["due"] == "2026-03-14T12:30:00Z"


@pytest.mark.parametrize("field", ["created", "due", "expires"])
def test_naive_timestamps_are_rejected(field: str) -> None:
    rejects(SEEK | {field: "2026-03-14T12:30:00"}, "timezone")


@pytest.mark.parametrize(
    ("data", "match"),
    [
        (GO | {"target": None}, "a go intention needs a target"),
        (SEEK | {"target": None}, "a seek intention needs a target"),
        (SEEK | {"target": "mei"}, "can't seek themselves"),
        (CREATE | {"owner": PLAYER_ID, "promised_to": []}, "player doesn't have intentions"),
        (CREATE | {"promised_to": ["mei", "viktor"]}, "can't promise themselves"),
        (SEEK | {"promised_to": ["viktor", "viktor"]}, "each person once"),
        (SEEK | {"due": "2026-03-14T08:00:00Z"}, "due must not be before created"),
        (SEEK | {"expires": SEEK["due"]}, "expires must be after due"),
        (SEEK | {"expires": "2026-03-14T12:00:00Z"}, "expires must be after due"),
        (CREATE | {"kind": "wander"}, "'create', 'go', 'seek' or 'news'"),
        (CREATE | {"description": ""}, "at least 1 character"),
        (CREATE | {"description": "x" * 241}, "at most 240 characters"),
        (GO | {"target": "The Park"}, "pattern"),
        (CREATE | {"status": "open"}, "Extra inputs are not permitted"),
    ],
)
def test_invalid_intentions_are_rejected(data: dict[str, Any], match: str) -> None:
    rejects(data, match)
