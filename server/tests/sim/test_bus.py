from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from simile.schema import Conversation, Line
from simile.sim import ConversationEnded, EntityMoved, Event, EventBus, LineSpoken

NOW = datetime(2026, 1, 1, 8, tzinfo=UTC)
LINE = Line(id=1, conversation_id="c1", speaker="ada", text="Morning.", timestamp=NOW, duration=1.2)
CONVERSATION = Conversation(
    id="c1", participants=["ada", "bo"], started=NOW, ended=NOW, lines=[LINE]
)

MOVED = EntityMoved("ada", 1.0, 2.0)
SPOKEN = LineSpoken(LINE)


def test_delivers_events_of_the_subscribed_type() -> None:
    bus = EventBus()
    moves: list[EntityMoved] = []
    bus.subscribe(EntityMoved, moves.append)

    bus.publish(MOVED)
    bus.publish(SPOKEN)

    assert moves == [MOVED]


def test_subscribing_to_event_receives_everything() -> None:
    bus = EventBus()
    events: list[Event] = []
    bus.subscribe(Event, events.append)

    bus.publish(MOVED)
    bus.publish(SPOKEN)

    assert events == [MOVED, SPOKEN]


def test_events_from_other_modules_subclass_event() -> None:
    @dataclass(frozen=True)
    class NewsRead(Event):
        npc_id: str
        news_id: str

    bus = EventBus()
    events: list[Event] = []
    bus.subscribe(Event, events.append)

    bus.publish(NewsRead("ada", "n1"))

    assert events == [NewsRead("ada", "n1")]


def test_unsubscribe_ends_only_its_own_subscription() -> None:
    bus = EventBus()
    events: list[Event] = []
    unsubscribe = bus.subscribe(Event, events.append)
    bus.subscribe(Event, events.append)

    unsubscribe()
    unsubscribe()
    bus.publish(MOVED)

    assert events == [MOVED]


def test_subscribers_are_called_in_order() -> None:
    bus = EventBus()
    calls: list[str] = []
    bus.subscribe(Event, lambda event: calls.append("first"))
    bus.subscribe(EntityMoved, lambda event: calls.append("second"))

    bus.publish(MOVED)

    assert calls == ["first", "second"]


def test_a_failing_subscriber_is_logged_and_others_still_run(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bus = EventBus()
    events: list[Event] = []

    def broken(event: Event) -> None:
        raise RuntimeError("boom")

    bus.subscribe(Event, broken)
    bus.subscribe(Event, events.append)

    bus.publish(ConversationEnded(CONVERSATION))

    assert events == [ConversationEnded(CONVERSATION)]
    assert "boom" in caplog.text
