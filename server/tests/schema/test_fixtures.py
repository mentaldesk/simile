import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter

from simile.schema import (
    PLAYER_ID,
    Conversation,
    InteractionEvent,
    Location,
    Memory,
    Model,
    NewsItem,
    Npc,
    Relationship,
    Work,
)

FIXTURES = Path(__file__).parents[1] / "fixtures"

LISTS: dict[str, type[Model]] = {
    "locations.json": Location,
    "relationships.json": Relationship,
    "interaction_events.json": InteractionEvent,
    "memories.json": Memory,
    "news_items.json": NewsItem,
    "works.json": Work,
    "conversations.json": Conversation,
}


def cases() -> list[Any]:
    found = [
        pytest.param(Npc, json.loads(path.read_text()), id=f"npcs/{path.name}")
        for path in sorted((FIXTURES / "npcs").glob("*.json"))
    ]
    for name, model in LISTS.items():
        for index, item in enumerate(json.loads((FIXTURES / name).read_text())):
            found.append(pytest.param(model, item, id=f"{name}[{index}]"))
    return found


def load[T: Model](name: str, model: type[T]) -> list[T]:
    return TypeAdapter(list[model]).validate_json((FIXTURES / name).read_bytes())


@pytest.mark.parametrize(("model", "data"), cases())
def test_fixture_round_trips_through_json(model: type[Model], data: dict[str, Any]) -> None:
    parsed = model.model_validate_json(json.dumps(data))
    dumped = parsed.model_dump_json()

    assert json.loads(dumped) == data
    assert model.model_validate_json(dumped) == parsed


def test_fixtures_refer_to_each_other() -> None:
    npcs = [Npc.model_validate_json(p.read_bytes()) for p in (FIXTURES / "npcs").glob("*.json")]
    entities = {npc.id for npc in npcs} | {PLAYER_ID}
    locations = {location.id for location in load("locations.json", Location)}
    conversations = load("conversations.json", Conversation)
    conversation_ids = {conversation.id for conversation in conversations} | {None}
    news_ids = {item.id for item in load("news_items.json", NewsItem)} | {None}
    works = load("works.json", Work)
    crafts = {npc.id: npc.craft for npc in npcs}

    assert {npc.home for npc in npcs} <= locations
    for work in works:
        craft = crafts[work.artist]
        assert craft is not None
        assert (work.medium, work.form) == (craft.medium, craft.form)
        assert set(work.inspired_by) <= news_ids | conversation_ids
    for conversation in conversations:
        assert set(conversation.participants) <= entities
    for rel in load("relationships.json", Relationship):
        assert {rel.owner, rel.about} <= entities
    for event in load("interaction_events.json", InteractionEvent):
        assert {event.actor, event.target} <= entities
        assert event.conversation_id in conversation_ids
    for memory in load("memories.json", Memory):
        assert {memory.owner, *memory.about} <= entities
        assert memory.conversation_id in conversation_ids
        assert memory.news_id in news_ids
        assert memory.work_id in {work.id for work in works} | {None}


def test_line_ids_are_unique() -> None:
    ids = [line.id for c in load("conversations.json", Conversation) for line in c.lines]

    assert len(ids) == len(set(ids))
