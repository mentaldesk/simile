import asyncio
from datetime import UTC, datetime

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.app import create_app
from simile.protocol import (
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


def forwarded(*events: Event) -> list[ServerMessage]:
    app = Starlette()
    world = app.state.world = World(Clock(NOW))
    sent: list[ServerMessage] = []
    hub_of(app).broadcast = sent.append

    async def run() -> None:
        async with lifespan(app):
            for event in events:
                world.bus.publish(event)
        world.bus.publish(EntityMoved("viktor", 1, 1))

    asyncio.run(run())
    return sent


@pytest.mark.parametrize(("event", "message"), CASES)
def test_forwards_sim_events_to_clients(event: Event, message: ServerMessage) -> None:
    assert forwarded(event) == [message]


def test_ignores_other_events() -> None:
    assert forwarded(Event()) == []


def test_clients_receive_events_published_on_the_bus() -> None:
    app = create_app()
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        ws.receive_json()

        client.portal.call(world_of(app).bus.publish, EntityMoved("suki", 18, 7.5))

        assert ws.receive_json() == {
            "type": "entity_moved",
            "entity_id": "suki",
            "position": {"x": 18, "y": 7.5},
        }
