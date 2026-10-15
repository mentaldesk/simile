from dataclasses import dataclass

import pytest

from simile.sim import ConversationEnded, EntityMoved, Event, EventBus, LineSpoken

MOVED = EntityMoved("ada", 1.0, 2.0)
SPOKEN = LineSpoken("c1", "ada", "Morning.")


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


def test_unsubscribe_stops_delivery() -> None:
    bus = EventBus()
    events: list[Event] = []
    unsubscribe = bus.subscribe(Event, events.append)

    unsubscribe()
    unsubscribe()
    bus.publish(MOVED)

    assert events == []


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

    bus.publish(ConversationEnded("c1"))

    assert events == [ConversationEnded("c1")]
    assert "boom" in caplog.text
