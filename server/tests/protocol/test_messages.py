import json
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from simile.protocol import (
    ClockMessage,
    ConversationEndedMessage,
    ConversationStartedMessage,
    EntityMovedMessage,
    LineMessage,
    ListNewsMessage,
    NewsArticle,
    NewsMessage,
    NpcStateMessage,
    PlayerMoveMessage,
    PlayerSayMessage,
    Position,
    ReadNewsMessage,
    WatchNpcMessage,
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

CLOCK = ClockMessage(time=SNAPSHOT.time, speed=60)
SERVER = [
    SNAPSHOT,
    EntityMovedMessage(entity_id="mei", position=Position(x=4.5, y=6)),
    ConversationStartedMessage(conversation=CONVERSATION.model_copy(update={"lines": []})),
    ConversationEndedMessage(
        conversation_id=CONVERSATION.id, ended=datetime(2026, 3, 14, 9, 11, tzinfo=UTC)
    ),
    LineMessage(line=CONVERSATION.lines[-1], voiced=True),
    NpcStateMessage(npc_id="mei", state={"goal": "coffee_shop", "values": {"connection": 0.92}}),
    NewsMessage(articles=[ARTICLE, ARTICLE.model_copy(update={"news_id": "n2", "read": True})]),
    CLOCK,
]
CLIENT = [
    PlayerMoveMessage(position=Position(x=14, y=12.25)),
    PlayerSayMessage(text="Hello!", target="mei"),
    WatchNpcMessage(npc_id="mei"),
    WatchNpcMessage(npc_id=None),
    ListNewsMessage(),
    ReadNewsMessage(news_id=ARTICLE.news_id),
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
        "position": {"x": 4.5, "y": 6.0},
    }


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


def test_timestamps_are_utc() -> None:
    sydney = datetime(2026, 3, 14, 20, 10, 3, tzinfo=timezone(timedelta(hours=11)))

    assert json.loads(fixture_snapshot(sydney).model_dump_json())["time"] == "2026-03-14T09:10:03Z"


@pytest.mark.parametrize(
    "data",
    [
        {"type": "snapshot"},
        {"type": "player_move", "position": {"x": 1, "y": 2}, "speed": 3},
        {"type": "player_say", "text": "", "target": "mei"},
        {"type": "player_say", "text": "Hi", "target": "Mei"},
        {"type": "watch_npc"},
        {"type": "watch_npc", "npc_id": "Mei"},
        {"type": "list_news", "news_id": "n1"},
        {"type": "read_news"},
        {"type": "read_news", "news_id": ""},
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
