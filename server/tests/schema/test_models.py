import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from simile.schema import (
    PLAYER_ID,
    Conversation,
    CoreValue,
    InteractionEvent,
    Model,
    Npc,
    Relationship,
)

FIXTURES = Path(__file__).parents[1] / "fixtures"


def fixture(name: str, index: int | None = None) -> dict[str, Any]:
    data = json.loads((FIXTURES / name).read_text())
    return data if index is None else data[index]


def rejects(model: type[Model], data: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        model.model_validate(data)


def test_there_are_24_core_values() -> None:
    assert len(CoreValue) == 24


def test_npc_needs_every_core_value() -> None:
    npc = fixture("npcs/mei.json")
    del npc["values"]["optimism"]

    rejects(Npc, npc, "missing core values: optimism")


def test_npc_cannot_take_the_player_id() -> None:
    rejects(Npc, fixture("npcs/mei.json") | {"id": PLAYER_ID}, "reserved for the player")


def test_ids_are_slugs() -> None:
    rejects(Npc, fixture("npcs/mei.json") | {"id": "Mei Lin"}, "String should match pattern")


def test_unknown_fields_are_rejected() -> None:
    rejects(Npc, fixture("npcs/mei.json") | {"mood": "sleepy"}, "Extra inputs are not permitted")


def test_colours_are_hex() -> None:
    npc = fixture("npcs/mei.json")
    npc["appearance"]["skin"] = "tan"

    rejects(Npc, npc, "String should match pattern")


@pytest.mark.parametrize("score", [-0.1, 1.1])
def test_relationship_scores_stay_in_unit_range(score: float) -> None:
    rejects(Relationship, fixture("relationships.json", 1) | {"trust": score}, "trust")


def test_relationship_needs_two_parties() -> None:
    rejects(Relationship, fixture("relationships.json", 1) | {"about": "viktor"}, "must differ")


def test_relationship_flags_belong_to_it() -> None:
    rel = fixture("relationships.json", 0)
    rel["flags"][0]["about"] = "suki"

    rejects(Relationship, rel, "belongs to another relationship")


@pytest.mark.parametrize("valence", [-1.5, 1.5])
def test_event_valence_is_signed_unit(valence: float) -> None:
    rejects(
        InteractionEvent, fixture("interaction_events.json", 0) | {"valence": valence}, "valence"
    )


def test_event_needs_two_parties() -> None:
    rejects(
        InteractionEvent,
        fixture("interaction_events.json", 0) | {"target": "viktor"},
        "must differ",
    )


def test_conversation_lines_come_from_participants() -> None:
    conversation = fixture("conversations.json", 0)
    conversation["lines"][0]["speaker"] = "suki"

    rejects(Conversation, conversation, "isn't a participant")


def test_conversation_lines_belong_to_it() -> None:
    conversation = fixture("conversations.json", 0)
    conversation["lines"][0]["conversation_id"] = "conv_2"

    rejects(Conversation, conversation, "belongs to conversation conv_2")


def test_conversation_participants_are_distinct() -> None:
    rejects(
        Conversation,
        fixture("conversations.json", 0) | {"participants": ["mei", "mei"], "lines": []},
        "distinct",
    )
