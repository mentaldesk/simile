import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.app import create_app
from simile.protocol import (
    ClockMessage,
    ConversationEndedMessage,
    ConversationStartedMessage,
    EntityMovedMessage,
    LineMessage,
    Position,
    ServerMessage,
    hub_of,
)
from simile.protocol.fixtures import fixture_world
from simile.protocol.lifespan import lifespan
from simile.sim import (
    STEP,
    Clock,
    ConversationEnded,
    ConversationStarted,
    EntityMoved,
    Event,
    LineSpoken,
    World,
    world_of,
)

NOW = datetime(2026, 3, 14, 9, 11, tzinfo=UTC)
TICK = timedelta(seconds=STEP)
CONVERSATION = fixture_world()[1][0]
LINE = CONVERSATION.lines[-1]

CASES = [
    pytest.param(
        EntityMoved("mei", 4.5, 6),
        EntityMovedMessage(entity_id="mei", position=Position(x=4.5, y=6)),
        id="entity_moved",
    ),
    pytest.param(
        ConversationStarted(CONVERSATION),
        ConversationStartedMessage(conversation=CONVERSATION),
        id="conversation_started",
    ),
    pytest.param(LineSpoken(LINE), LineMessage(line=LINE, voiced=False), id="line"),
    pytest.param(
        ConversationEnded(CONVERSATION.model_copy(update={"ended": NOW})),
        ConversationEndedMessage(conversation_id=CONVERSATION.id, ended=NOW),
        id="conversation_ended",
    ),
    pytest.param(
        ConversationEnded(CONVERSATION),
        ConversationEndedMessage(conversation_id=CONVERSATION.id, ended=NOW),
        id="conversation_ended_without_ended_uses_the_clock",
    ),
]


def sent_by(act: Callable[[World], None]) -> list[ServerMessage]:
    app = Starlette()
    world = app.state.world = World(Clock(NOW))
    sent: list[ServerMessage] = []
    hub_of(app).broadcast = sent.append

    async def run() -> None:
        async with lifespan(app):
            act(world)
        act(world)

    asyncio.run(run())
    return sent


def forwarded(*events: Event) -> list[ServerMessage]:
    def publish(world: World) -> None:
        for event in events:
            world.bus.publish(event)

    return sent_by(publish)


def ticks(world: World, count: int) -> None:
    for _ in range(count):
        world.loop.tick()


@pytest.mark.parametrize(("event", "message"), CASES)
def test_forwards_sim_events_to_clients(event: Event, message: ServerMessage) -> None:
    assert forwarded(event) == [message]


def test_ignores_other_events() -> None:
    assert forwarded(Event()) == []


def test_broadcasts_the_clock_when_the_speed_changes() -> None:
    def speed_up(world: World) -> None:
        ticks(world, 1)
        world.clock.speed = 10
        ticks(world, 2)

    assert sent_by(speed_up) == [ClockMessage(time=NOW + 2 * TICK, speed=10)]


def test_broadcasts_the_clock_as_each_sim_minute_starts() -> None:
    sent = sent_by(lambda world: ticks(world, round(120 / STEP)))

    assert sent == [
        ClockMessage(time=NOW + timedelta(minutes=1), speed=1),
        ClockMessage(time=NOW + timedelta(minutes=2), speed=1),
    ]


def test_greets_new_clients_with_the_clock_while_running() -> None:
    app = Starlette()
    world = app.state.world = World(Clock(NOW, speed=4))
    hub = hub_of(app)

    async def run() -> None:
        async with lifespan(app):
            world.loop.tick()
            assert hub.clock is not None
            assert hub.clock() == ClockMessage(time=NOW + TICK, speed=4)

    asyncio.run(run())
    assert hub.clock is None


def test_clients_receive_events_published_on_the_bus() -> None:
    app = create_app()
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "snapshot"
        assert ws.receive_json()["type"] == "clock"
        assert ws.receive_json()["type"] == "murals"

        client.portal.call(world_of(app).bus.publish, EntityMoved("suki", 18, 7.5))

        assert ws.receive_json() == {
            "type": "entity_moved",
            "entity_id": "suki",
            "position": {"x": 18, "y": 7.5},
        }
