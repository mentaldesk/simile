import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from simile.schema import (
    PLAYER_ID,
    Character,
    CharacterSource,
    CharacterVoice,
    Gender,
    Hook,
    HookKind,
    HookSide,
    Memory,
    MemoryKind,
    Model,
    Npc,
    PastMemory,
    Traits,
    Voice,
    export,
)

CHARACTERS = Path(__file__).parent / "characters"
FIXTURES = Path(__file__).parents[1] / "fixtures"
PATHS = sorted(CHARACTERS.glob("*.json"))


def character(name: str = "premade") -> dict[str, Any]:
    return json.loads((CHARACTERS / f"{name}.json").read_text())


def rejects(model: type[Model], data: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        model.model_validate(data)


def test_there_is_a_premade_and_a_player_fixture() -> None:
    sources = {Character.model_validate_json(path.read_bytes()).source for path in PATHS}

    assert sources == set(CharacterSource)


@pytest.mark.parametrize("path", PATHS, ids=lambda path: path.name)
def test_fixture_round_trips_through_json(path: Path) -> None:
    data = json.loads(path.read_text())

    parsed = Character.model_validate_json(path.read_bytes())
    dumped = parsed.model_dump_json()

    assert json.loads(dumped) == data
    assert Character.model_validate_json(dumped) == parsed


@pytest.mark.parametrize("path", PATHS, ids=lambda path: path.name)
def test_exported_schema_accepts_fixtures(path: Path) -> None:
    schema = Draft202012Validator(json.loads((export.JSON_DIR / "Character.json").read_text()))

    schema.validate(json.loads(path.read_text()))
    assert not schema.is_valid(json.loads(path.read_text()) | {"home": "house_1"})


def test_a_character_has_no_home_or_age() -> None:
    rejects(Character, character() | {"home": "house_1"}, "home\n  Extra inputs")
    rejects(Character, character() | {"age": 58}, "age\n  Extra inputs")


def test_a_character_needs_every_core_value() -> None:
    data = character()
    del data["values"]["optimism"]

    rejects(Character, data, "missing core values: optimism")


def test_a_character_cannot_take_the_player_id() -> None:
    rejects(Character, character() | {"id": PLAYER_ID}, "reserved for the player")


@pytest.mark.parametrize(
    ("update", "match"),
    [
        ({"id": "Danuta Sobczak"}, "String should match pattern"),
        ({"gender": "other"}, "gender"),
        ({"source": "imported"}, "source"),
        ({"version": 0}, "version"),
        ({"traits": {"sociability": 1.2}}, "traits.sociability"),
        ({"arrival": {"age": 34, "reason": ""}}, "arrival.reason"),
        ({"arrival": {"age": -1, "reason": "for a job"}}, "arrival.age"),
    ],
)
def test_character_fields_follow_the_rules(update: dict[str, Any], match: str) -> None:
    rejects(Character, character() | update, match)


@pytest.mark.parametrize(
    "field", ["name", "origin", "occupation", "backstory", "persona", "speaking_style"]
)
def test_character_text_is_not_empty(field: str) -> None:
    rejects(Character, character() | {field: ""}, "at least 1 character")


@pytest.mark.parametrize("gender", list(Gender))
def test_any_gender_loads(gender: Gender) -> None:
    assert Character.model_validate(character() | {"gender": gender}).gender is gender


def test_someone_born_in_the_village_has_no_arrival() -> None:
    parsed = Character.model_validate(character() | {"arrival": None})

    assert parsed.arrival is None
    assert json.loads(parsed.model_dump_json())["arrival"] is None


def test_arrival_is_required() -> None:
    data = character()
    del data["arrival"]

    rejects(Character, data, "arrival\n  Field required")


def test_a_character_without_a_craft_loads_with_none() -> None:
    data = character("player")
    del data["craft"]

    assert Character.model_validate(data).craft is None


@pytest.mark.parametrize("field", ["created", "updated"])
def test_naive_timestamps_are_rejected(field: str) -> None:
    rejects(Character, character() | {field: "2026-10-01T09:00:00"}, "timezone")


def test_timestamps_are_converted_to_utc() -> None:
    stamp = "2026-10-01T17:00:00+08:00"
    parsed = Character.model_validate(character() | {"created": stamp, "updated": stamp})

    assert parsed.created == parsed.updated == datetime(2026, 10, 1, 9, tzinfo=UTC)
    assert json.loads(parsed.model_dump_json())["created"] == "2026-10-01T09:00:00Z"


def test_updated_is_not_before_created() -> None:
    rejects(
        Character,
        character() | {"updated": "2026-09-30T09:00:00Z"},
        "updated must not be before created",
    )


@pytest.mark.parametrize(("birth_year", "match"), [(2027, "be -1 in 2026"), (1905, "be 121")])
def test_age_at_the_last_edit_is_possible(birth_year: int, match: str) -> None:
    rejects(Character, character() | {"birth_year": birth_year}, match)


def test_the_past_can_reach_their_current_age() -> None:
    data = character()
    data["past"][-1]["age"] = 58
    data["arrival"]["age"] = 58

    assert Character.model_validate(data).past[-1].age == 58


def test_a_past_memory_is_not_older_than_they_are() -> None:
    data = character()
    data["past"][-1]["age"] = 59

    rejects(Character, data, "something happened at 59, but they're at most 58")


def test_they_arrive_no_older_than_they_are() -> None:
    data = character()
    data["arrival"]["age"] = 59

    rejects(Character, data, "something happened at 59, but they're at most 58")


@pytest.mark.parametrize(
    ("update", "match"),
    [
        ({"age": -1}, "age"),
        ({"age": 121}, "age"),
        ({"content": ""}, "at least 1 character"),
        ({"salience": 1.1}, "salience"),
        ({"valence": -1.5}, "valence"),
    ],
)
def test_past_memory_fields_follow_the_rules(update: dict[str, Any], match: str) -> None:
    rejects(PastMemory, character()["past"][0] | update, match)


@pytest.mark.parametrize("kind", list(HookKind))
def test_a_hook_is_mutual_or_has_a_side(kind: HookKind) -> None:
    fits = [HookSide.MUTUAL] if kind.mutual else [HookSide.ACTOR, HookSide.TARGET]
    hook = {"kind": kind, "description": "An old tie."}

    for side in HookSide:
        if side in fits:
            assert Hook.model_validate(hook | {"side": side}).side is side
        else:
            rejects(Hook, hook | {"side": side}, f"a {kind} hook's side is")


def test_mutual_hooks() -> None:
    assert {kind for kind in HookKind if kind.mutual} == {
        HookKind.ESTRANGED_SIBLING,
        HookKind.EX_PARTNER,
        HookKind.OLD_FRIEND,
        HookKind.RIVAL,
    }


@pytest.mark.parametrize(
    ("update", "match"),
    [
        ({"kind": "cousin"}, "kind"),
        ({"side": "both"}, "side"),
        ({"description": ""}, "at least 1 character"),
    ],
)
def test_hook_fields_follow_the_rules(update: dict[str, Any], match: str) -> None:
    rejects(Hook, character()["hooks"][0] | update, match)


def test_traits_default_to_neutral() -> None:
    assert Traits() == Traits(
        sociability=0.5, negativity_bias=0.5, forgiveness=0.5, first_impressions=0.5
    )


def test_needs_recording_defaults_to_false() -> None:
    voice = character()["voice"]
    del voice["needs_recording"]

    assert CharacterVoice.model_validate(voice).needs_recording is False


def test_a_character_voice_on_an_npc_keeps_the_npc_json() -> None:
    npc = json.loads((FIXTURES / "npcs" / "viktor.json").read_text())
    voice = CharacterVoice.model_validate(npc["voice"] | {"needs_recording": True})

    assert isinstance(voice, Voice)
    assert json.loads(Npc.model_validate(npc | {"voice": voice}).model_dump_json()) == npc


def test_a_past_memory_can_be_stored() -> None:
    memory = json.loads((FIXTURES / "memories.json").read_text())[0]
    memory |= {"kind": "past", "conversation_id": None}

    assert Memory.model_validate(memory).kind is MemoryKind.PAST
