import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from simile.schema import (
    PLAYER_ID,
    VILLAGE_MAP,
    Conversation,
    CoreValue,
    Craft,
    Door,
    Flag,
    Interactable,
    InteractableKind,
    InteractionEvent,
    Line,
    Location,
    LocationKind,
    MapTile,
    Medium,
    Memory,
    Model,
    NewsItem,
    Npc,
    Relationship,
    Tile,
    TileArea,
    Work,
)
from simile.world.map import load_map

from .conftest import COUNTER, DOOR

FIXTURES = Path(__file__).parents[1] / "fixtures"
CONTENT_NPCS = Path(__file__).parents[3] / "content" / "npcs"


def fixture(name: str, index: int | None = None) -> dict[str, Any]:
    data = json.loads((FIXTURES / name).read_text())
    return data if index is None else data[index]


def rejects(model: type[Model], data: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        model.model_validate(data)


PAINTING = fixture("works.json", 1) | {
    "id": "work_4",
    "medium": "painting",
    "form": "small oils of the river at low tide",
    "wall": None,
}

TIMESTAMPS = [
    (Conversation, fixture("conversations.json", 0), "started"),
    (Conversation, fixture("conversations.json", 0), "ended"),
    (Line, fixture("conversations.json", 0)["lines"][0], "timestamp"),
    (InteractionEvent, fixture("interaction_events.json", 0), "timestamp"),
    (Flag, fixture("relationships.json", 0)["flags"][0], "created"),
    (Flag, fixture("relationships.json", 0)["flags"][0], "resolved"),
    (Relationship, fixture("relationships.json", 1), "last_interaction"),
    (Memory, fixture("memories.json", 0), "timestamp"),
    (NewsItem, fixture("news_items.json", 0), "published"),
    (Work, fixture("works.json", 0), "created"),
]


@pytest.mark.parametrize(("model", "data", "field"), TIMESTAMPS)
def test_naive_timestamps_are_rejected(
    model: type[Model], data: dict[str, Any], field: str
) -> None:
    rejects(model, data | {field: "2026-03-14T16:05:00"}, "timezone")


@pytest.mark.parametrize(("model", "data", "field"), TIMESTAMPS)
def test_timestamps_are_converted_to_utc(
    model: type[Model], data: dict[str, Any], field: str
) -> None:
    parsed = model.model_validate(data | {field: "2026-03-14T16:05:00+08:00"})

    assert getattr(parsed, field) == datetime(2026, 3, 14, 8, 5, tzinfo=UTC)
    assert getattr(parsed, field).tzinfo is UTC
    assert json.loads(parsed.model_dump_json())[field] == "2026-03-14T08:05:00Z"


@pytest.mark.parametrize(
    ("model", "data"),
    [
        (Line, fixture("conversations.json", 0)["lines"][0]),
        (InteractionEvent, fixture("interaction_events.json", 2)),
        (Memory, fixture("memories.json", 0)),
    ],
)
def test_conversation_ids_are_not_empty(model: type[Model], data: dict[str, Any]) -> None:
    rejects(model, data | {"conversation_id": ""}, "at least 1 character")


def test_memory_work_ids_are_not_empty() -> None:
    rejects(Memory, fixture("memories.json", 6) | {"work_id": ""}, "at least 1 character")


def test_memories_stored_before_works_load_without_a_work() -> None:
    memory = fixture("memories.json", 0)
    del memory["work_id"]

    assert Memory.model_validate_json(json.dumps(memory)).work_id is None


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


@pytest.mark.parametrize("path", sorted(CONTENT_NPCS.glob("*.json")), ids=lambda path: path.name)
def test_committed_npcs_still_load(path: Path) -> None:
    Npc.model_validate_json(path.read_bytes())


def test_npcs_without_a_craft_load_with_none() -> None:
    npc = fixture("npcs/viktor.json")
    del npc["craft"]

    assert Npc.model_validate_json(json.dumps(npc)).craft is None


def test_npc_craft_round_trips() -> None:
    npc = Npc.model_validate(fixture("npcs/viktor.json"))

    assert npc.craft == Craft(medium=Medium.WRITING, form="plain verse about old bridges")
    assert Npc.model_validate_json(npc.model_dump_json()) == npc


@pytest.mark.parametrize("medium", ["writing", "mural", "painting"])
def test_a_craft_can_be_writing_murals_or_paintings(medium: str) -> None:
    craft = {"medium": medium, "form": "small oils of the river at low tide"}

    npc = Npc.model_validate(fixture("npcs/viktor.json") | {"craft": craft})

    assert npc.craft == Craft.model_validate(craft)


@pytest.mark.parametrize(
    ("craft", "match"),
    [
        ({"medium": "music", "form": "sea shanties"}, "medium"),
        ({"medium": "writing", "form": ""}, "at least 1 character"),
        ({"medium": "writing"}, "form"),
    ],
)
def test_crafts_are_a_known_medium_and_a_form(craft: dict[str, Any], match: str) -> None:
    rejects(Npc, fixture("npcs/viktor.json") | {"craft": craft}, match)


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


def test_news_items_stored_without_a_source_still_load() -> None:
    item = fixture("news_items.json", 0)
    del item["source"], item["source_url"]

    parsed = NewsItem.model_validate_json(json.dumps(item))

    assert (parsed.source, parsed.source_url) == ("", "")


def test_news_items_stored_before_analysis_load_as_not_analysed() -> None:
    item = fixture("news_items.json", 1)
    del item["values"], item["tags"], item["sentiment"]

    parsed = NewsItem.model_validate_json(json.dumps(item))

    assert (parsed.values, parsed.tags, parsed.sentiment) == ({}, [], None)
    assert not parsed.analysed


def test_news_item_with_values_is_analysed() -> None:
    assert NewsItem.model_validate(fixture("news_items.json", 1)).analysed


@pytest.mark.parametrize("score", [-0.1, 1.1])
def test_news_relatedness_stays_in_unit_range(score: float) -> None:
    item = fixture("news_items.json", 1)
    item["values"]["freedom"] = score

    rejects(NewsItem, item, "values.freedom")


def test_news_values_are_all_or_nothing() -> None:
    item = fixture("news_items.json", 1)
    del item["values"]["optimism"]

    rejects(NewsItem, item, "missing core values: optimism")


@pytest.mark.parametrize(
    ("tags", "match"),
    [
        ([f"tag {n}" for n in range(11)], "at most 10 items"),
        ([""], "at least 1 character"),
        (["x" * 41], "at most 40 characters"),
    ],
)
def test_news_tags_are_few_and_short(tags: list[str], match: str) -> None:
    rejects(NewsItem, fixture("news_items.json", 1) | {"tags": tags}, match)


@pytest.mark.parametrize("sentiment", [-1.5, 1.5])
def test_news_sentiment_is_signed_unit(sentiment: float) -> None:
    rejects(NewsItem, fixture("news_items.json", 1) | {"sentiment": sentiment}, "sentiment")


def test_a_mural_is_on_a_wall() -> None:
    rejects(Work, fixture("works.json", 1) | {"wall": None}, "a mural needs a wall")


def test_writing_is_not_on_a_wall() -> None:
    rejects(Work, fixture("works.json", 0) | {"wall": "square_north"}, "only a mural has one")


def test_a_painting_hangs_without_a_wall() -> None:
    painting = Work.model_validate(PAINTING)

    assert painting.medium is Medium.PAINTING
    assert painting.wall is None
    assert Work.model_validate_json(painting.model_dump_json()) == painting


def test_a_painting_is_not_on_a_wall() -> None:
    rejects(Work, PAINTING | {"wall": "square_north"}, "only a mural has one")


def test_a_work_relates_to_every_core_value() -> None:
    work = fixture("works.json", 0)
    del work["values"]["optimism"]

    rejects(Work, work, "missing core values: optimism")


@pytest.mark.parametrize("field", ["values", "tags", "sentiment"])
def test_a_work_is_always_analysed(field: str) -> None:
    work = fixture("works.json", 0)
    del work[field]

    rejects(Work, work, f"{field}\n  Field required")


@pytest.mark.parametrize(
    ("update", "match"),
    [
        ({"values": fixture("works.json", 0)["values"] | {"freedom": 1.1}}, "values.freedom"),
        ({"tags": [f"tag {n}" for n in range(11)]}, "at most 10 items"),
        ({"tags": ["x" * 41]}, "at most 40 characters"),
        ({"sentiment": -1.5}, "sentiment"),
        ({"artist": "Viktor"}, "String should match pattern"),
        ({"medium": "music"}, "medium"),
        ({"form": ""}, "at least 1 character"),
        ({"title": ""}, "at least 1 character"),
        ({"inspired_by": [""]}, "at least 1 character"),
    ],
)
def test_work_fields_follow_the_rules(update: dict[str, Any], match: str) -> None:
    rejects(Work, fixture("works.json", 0) | update, match)


def test_locations_stored_without_a_map_are_on_the_village() -> None:
    location = fixture("locations.json", 0)
    del location["map"]

    assert Location.model_validate_json(json.dumps(location)).map == VILLAGE_MAP


def test_the_committed_village_map_still_loads_onto_the_village() -> None:
    locations = load_map().locations

    assert locations
    assert {location.map for location in locations} == {VILLAGE_MAP}


@pytest.mark.parametrize("kind", ["gallery", "maker_space", "noodle_bar"])
def test_a_location_can_be_inside_a_building(kind: str) -> None:
    location = Location.model_validate(
        fixture("locations.json", 3) | {"id": kind, "kind": kind, "map": kind}
    )

    assert (location.kind, location.map) == (LocationKind(kind), kind)
    assert Location.model_validate_json(location.model_dump_json()) == location


def test_a_location_map_is_not_empty() -> None:
    rejects(Location, fixture("locations.json", 0) | {"map": ""}, "at least 1 character")


def test_a_door_round_trips() -> None:
    door = Door.model_validate(DOOR)

    assert door.outside == MapTile(map="village", x=31, y=13)
    assert door.inside == MapTile(map="coffee_shop", x=10, y=12)
    assert json.loads(door.model_dump_json()) == DOOR
    assert Door.model_validate_json(door.model_dump_json()) == door


def test_a_door_links_two_maps() -> None:
    inside = DOOR["inside"] | {"map": "village"}

    rejects(Door, DOOR | {"inside": inside}, "a door links two different maps")


@pytest.mark.parametrize(
    ("update", "match"),
    [
        ({"id": "Coffee Shop"}, "String should match pattern"),
        ({"outside": {"map": "", "x": 31, "y": 13}}, "at least 1 character"),
        ({"inside": {"map": "coffee_shop", "x": -1, "y": 12}}, "inside.x"),
        ({"inside": {"x": 10, "y": 12}}, "inside.map"),
    ],
)
def test_door_fields_follow_the_rules(update: dict[str, Any], match: str) -> None:
    rejects(Door, DOOR | update, match)


def test_an_interactable_round_trips() -> None:
    counter = Interactable.model_validate(COUNTER)

    assert counter.kind is InteractableKind.COUNTER
    assert counter.area == TileArea(x=6, y=4, width=6, height=1)
    assert counter.stand == [Tile(x=9, y=6)]
    assert json.loads(counter.model_dump_json()) == COUNTER
    assert Interactable.model_validate_json(counter.model_dump_json()) == counter


@pytest.mark.parametrize("kind", ["counter", "painting", "machine"])
def test_interactables_are_counters_paintings_or_machines(kind: str) -> None:
    assert Interactable.model_validate(COUNTER | {"kind": kind}).kind == InteractableKind(kind)


def test_an_interactable_can_be_used_from_several_tiles() -> None:
    stand = [{"x": 3, "y": 2}, {"x": 4, "y": 2}]

    assert Interactable.model_validate(COUNTER | {"stand": stand}).stand == [
        Tile(x=3, y=2),
        Tile(x=4, y=2),
    ]


@pytest.mark.parametrize(
    ("update", "match"),
    [
        ({"stand": []}, "at least 1 item"),
        ({"kind": "bench"}, "kind"),
        ({"label": ""}, "at least 1 character"),
        ({"map": ""}, "at least 1 character"),
        ({"id": "Counter"}, "String should match pattern"),
        ({"area": {"x": 6, "y": 4, "width": 0, "height": 1}}, "area.width"),
        ({"stand": [{"x": 9, "y": -1}]}, "stand.0.y"),
    ],
)
def test_interactable_fields_follow_the_rules(update: dict[str, Any], match: str) -> None:
    rejects(Interactable, COUNTER | update, match)
