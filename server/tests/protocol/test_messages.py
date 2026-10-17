import json
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import TypeAdapter, ValidationError
from pydantic.json_schema import JsonSchemaMode

from simile.protocol import (
    Artist,
    ClockMessage,
    ConversationEndedMessage,
    ConversationStartedMessage,
    EntityMovedMessage,
    Face,
    LineMessage,
    ListNewsMessage,
    ListWorksMessage,
    Message,
    Mural,
    MuralsMessage,
    NewsArticle,
    NewsMessage,
    NpcStateMessage,
    PlayerMoveMessage,
    PlayerSayMessage,
    Position,
    ReadNewsMessage,
    ReadWorkMessage,
    Wall,
    WatchNpcMessage,
    WorksMessage,
    WrittenWork,
)
from simile.protocol.export import SCHEMA_FILE
from simile.protocol.fixtures import fixture_snapshot
from simile.protocol.messages import client_messages, server_messages

SNAPSHOT = fixture_snapshot(datetime(2026, 3, 14, 9, 10, 3, tzinfo=UTC))
CONVERSATION = SNAPSHOT.conversations[0]
ARTICLE = NewsArticle(
    news_id="https://bigthink.com/?p=900101",
    title="Drones to be regulated",
    source="Big Think",
    summary="The council votes on drone rules.",
    url="https://bigthink.com/drones",
    read=False,
)

VIKTOR = Artist(id="viktor", name="Viktor Petrov")
POEM = WrittenWork(
    work_id="work_1",
    title="The Footbridge",
    artist=VIKTOR,
    form="plain verse about old bridges",
    text="They built it for a hundred years.\nThe arch has held for ninety-one.",
    statement="Things last when people look after them.",
    created=datetime(2026, 3, 14, 8, 40, tzinfo=UTC),
    read=False,
)
WORKS = WorksMessage(works=[POEM.model_copy(update={"work_id": "work_3", "read": True}), POEM])
MURAL = Mural(
    work_id="work_2",
    title="Who Owns the Sky",
    artist=Artist(id="suki", name="Suki Tanaka"),
    statement="The sky was the one place nobody filled with forms.",
    image="/api/works/work_2.png",
)
SQUARE_WALL = Wall(
    id="square_north", x=12, y=8, width=4, face=Face.SOUTH, bottom=0, top=1, mural=MURAL
)
MURALS = MuralsMessage(
    walls=[
        SQUARE_WALL,
        Wall(id="park_east", x=30, y=14, width=3, face=Face.EAST, bottom=0.2, top=2, mural=None),
    ]
)

CLOCK = ClockMessage(time=SNAPSHOT.time, speed=60)
SERVER = [
    SNAPSHOT,
    EntityMovedMessage(entity_id="mei", position=Position(x=4.5, y=6)),
    EntityMovedMessage(entity_id="suki", position=Position(x=10, y=12, map="coffee_shop")),
    ConversationStartedMessage(conversation=CONVERSATION.model_copy(update={"lines": []})),
    ConversationEndedMessage(
        conversation_id=CONVERSATION.id, ended=datetime(2026, 3, 14, 9, 11, tzinfo=UTC)
    ),
    LineMessage(line=CONVERSATION.lines[-1], voiced=True),
    NpcStateMessage(npc_id="mei", state={"goal": "coffee_shop", "values": {"connection": 0.92}}),
    NewsMessage(articles=[ARTICLE, ARTICLE.model_copy(update={"news_id": "n2", "read": True})]),
    CLOCK,
    WORKS,
    MURALS,
]
CLIENT = [
    PlayerMoveMessage(position=Position(x=14, y=12.25)),
    PlayerMoveMessage(position=Position(x=10, y=11.5, map="coffee_shop")),
    PlayerSayMessage(text="Hello!", target="mei"),
    WatchNpcMessage(npc_id="mei"),
    WatchNpcMessage(npc_id=None),
    ListNewsMessage(),
    ReadNewsMessage(news_id=ARTICLE.news_id),
    ListWorksMessage(),
    ReadWorkMessage(work_id=POEM.work_id),
]


def validator() -> Draft202012Validator:
    return Draft202012Validator(json.loads(SCHEMA_FILE.read_text()))


@pytest.mark.parametrize("message", SERVER, ids=lambda m: m.type)
def test_server_message_round_trips(message: Any) -> None:
    assert server_messages.validate_json(message.model_dump_json()) == message


@pytest.mark.parametrize("message", CLIENT, ids=lambda m: m.type)
def test_client_message_round_trips(message: Any) -> None:
    assert client_messages.validate_json(message.model_dump_json()) == message


@pytest.mark.parametrize("message", SERVER + CLIENT, ids=lambda m: m.type)
def test_exported_schema_accepts_message(message: Any) -> None:
    validator().validate(json.loads(message.model_dump_json()))


def test_messages_carry_their_type() -> None:
    assert json.loads(SERVER[1].model_dump_json()) == {
        "type": "entity_moved",
        "entity_id": "mei",
        "position": {"x": 4.5, "y": 6.0, "map": "village"},
    }


def test_positions_say_which_map_they_are_on() -> None:
    assert json.loads(SERVER[2].model_dump_json())["position"] == {
        "x": 10.0,
        "y": 12.0,
        "map": "coffee_shop",
    }


def test_a_client_that_sends_no_map_stays_on_the_village() -> None:
    data = {"type": "player_move", "position": {"x": 14, "y": 12.5}}

    validator().validate(data)
    assert client_messages.validate_python(data).position.map == "village"


def test_the_exported_position_has_a_map_but_does_not_require_it() -> None:
    position = json.loads(SCHEMA_FILE.read_text())["$defs"]["Position"]

    assert list(position["properties"]) == ["x", "y", "map"]
    assert position["required"] == ["x", "y"]


@pytest.mark.parametrize("mode", ["validation", "serialization"])
def test_a_position_schema_never_requires_a_map(mode: JsonSchemaMode) -> None:
    in_messages = TypeAdapter(Message).json_schema(mode=mode)["$defs"]["Position"]

    assert Position.model_json_schema(mode=mode)["required"] == ["x", "y"]
    assert in_messages["required"] == ["x", "y"]


def test_snapshot_entities_carry_their_map() -> None:
    entities = json.loads(SNAPSHOT.model_dump_json())["entities"]

    assert {entity["position"]["map"] for entity in entities} == {"village"}


def test_the_clock_carries_sim_time_and_speed() -> None:
    assert json.loads(CLOCK.model_dump_json()) == {
        "type": "clock",
        "time": "2026-03-14T09:10:03Z",
        "speed": 60.0,
    }


@pytest.mark.parametrize("speed", [0, -1])
def test_the_clock_never_stops_or_runs_backwards(speed: float) -> None:
    with pytest.raises(ValidationError):
        ClockMessage(time=SNAPSHOT.time, speed=speed)


def test_stopping_watching_sends_a_null_npc_id() -> None:
    assert json.loads(WatchNpcMessage(npc_id=None).model_dump_json()) == {
        "type": "watch_npc",
        "npc_id": None,
    }


def test_news_lists_every_field_of_each_article() -> None:
    assert json.loads(NewsMessage(articles=[ARTICLE]).model_dump_json()) == {
        "type": "news",
        "articles": [
            {
                "news_id": "https://bigthink.com/?p=900101",
                "title": "Drones to be regulated",
                "source": "Big Think",
                "summary": "The council votes on drone rules.",
                "url": "https://bigthink.com/drones",
                "read": False,
            }
        ],
    }


def test_works_lists_every_field_of_each_work() -> None:
    assert json.loads(WorksMessage(works=[POEM]).model_dump_json()) == {
        "type": "works",
        "works": [
            {
                "work_id": "work_1",
                "title": "The Footbridge",
                "artist": {"id": "viktor", "name": "Viktor Petrov"},
                "form": "plain verse about old bridges",
                "text": "They built it for a hundred years.\nThe arch has held for ninety-one.",
                "statement": "Things last when people look after them.",
                "created": "2026-03-14T08:40:00Z",
                "read": False,
            }
        ],
    }


def test_murals_lists_every_wall_with_its_mural_or_null() -> None:
    assert json.loads(MURALS.model_dump_json()) == {
        "type": "murals",
        "walls": [
            {
                "id": "square_north",
                "x": 12,
                "y": 8,
                "width": 4,
                "face": "south",
                "bottom": 0.0,
                "top": 1.0,
                "mural": {
                    "work_id": "work_2",
                    "title": "Who Owns the Sky",
                    "artist": {"id": "suki", "name": "Suki Tanaka"},
                    "statement": "The sky was the one place nobody filled with forms.",
                    "image": "/api/works/work_2.png",
                },
            },
            {
                "id": "park_east",
                "x": 30,
                "y": 14,
                "width": 3,
                "face": "east",
                "bottom": 0.2,
                "top": 2.0,
                "mural": None,
            },
        ],
    }


@pytest.mark.parametrize(
    ("update", "match"),
    [
        ({"face": "north"}, "face"),
        ({"width": 0}, "width"),
        ({"x": -1}, "x"),
        ({"bottom": -0.5}, "bottom"),
        ({"top": 0}, "top must be above bottom"),
        ({"id": "Square North"}, "String should match pattern"),
    ],
)
def test_rejects_invalid_walls(update: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        Wall.model_validate(SQUARE_WALL.model_dump() | update)


def test_timestamps_are_utc() -> None:
    sydney = datetime(2026, 3, 14, 20, 10, 3, tzinfo=timezone(timedelta(hours=11)))

    assert json.loads(fixture_snapshot(sydney).model_dump_json())["time"] == "2026-03-14T09:10:03Z"


@pytest.mark.parametrize(
    "data",
    [
        {"type": "snapshot"},
        {"type": "player_move", "position": {"x": 1, "y": 2}, "speed": 3},
        {"type": "player_move", "position": {"x": 1, "y": 2, "map": ""}},
        {"type": "player_move", "position": {"x": 1, "y": 2, "map": None}},
        {"type": "player_say", "text": "", "target": "mei"},
        {"type": "player_say", "text": "Hi", "target": "Mei"},
        {"type": "watch_npc"},
        {"type": "watch_npc", "npc_id": "Mei"},
        {"type": "list_news", "news_id": "n1"},
        {"type": "read_news"},
        {"type": "read_news", "news_id": ""},
        {"type": "list_works", "work_id": "work_1"},
        {"type": "read_work"},
        {"type": "read_work", "work_id": ""},
    ],
)
def test_rejects_invalid_client_messages(data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        client_messages.validate_python(data)


def test_fixture_snapshot_has_everyone_and_only_active_conversations() -> None:
    assert [(e.id, e.kind) for e in SNAPSHOT.entities] == [
        ("mei", "npc"),
        ("suki", "npc"),
        ("viktor", "npc"),
        ("player", "player"),
    ]
    assert SNAPSHOT.entities[0].position == Position(x=3, y=11)
    assert [c.id for c in SNAPSHOT.conversations] == ["conv_2"]
