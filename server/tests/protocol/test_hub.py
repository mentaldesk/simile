import logging
from collections.abc import Callable, Iterator
from datetime import UTC, datetime

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.app import create_app
from simile.protocol import (
    AudioChunk,
    EntityMovedMessage,
    Hub,
    PlayerMoveMessage,
    PlayerSayMessage,
    Position,
    SnapshotMessage,
    hub_of,
)
from simile.protocol.fixtures import fixture_snapshot
from simile.sim import Clock, World, world_of

MOVED = EntityMovedMessage(entity_id="viktor", position=Position(x=11, y=7.5))
START = datetime(2026, 3, 14, 9, tzinfo=UTC)


@pytest.fixture
def app(make_package: Callable[[dict[str, str]], str]) -> Starlette:
    app = create_app(
        make_package(
            {
                "protocol/lifespan.py": "from simile.protocol.lifespan import lifespan\n",
                "protocol/routes.py": "from simile.protocol.routes import routes\n",
                "sim/lifespan.py": "from simile.sim.lifespan import running\n",
            }
        )
    )
    app.state.world = World(Clock(START))
    return app


@pytest.fixture
def client(app: Starlette) -> Iterator[TestClient]:
    with TestClient(app) as client:
        yield client


@pytest.fixture
def hub(app: Starlette) -> Hub:
    return hub_of(app)


def test_sends_the_fixture_snapshot_at_sim_time_on_connect(
    app: Starlette, client: TestClient
) -> None:
    with client.websocket_connect("/ws") as ws:
        snapshot = SnapshotMessage.model_validate(ws.receive_json())

    assert START <= snapshot.time <= world_of(app).clock.now
    assert snapshot.model_copy(update={"time": START}) == fixture_snapshot(START)


def test_sends_the_snapshot_from_the_current_source(client: TestClient, hub: Hub) -> None:
    hub.snapshot = lambda: fixture_snapshot(START).model_copy(update={"map_id": "elsewhere"})

    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["map_id"] == "elsewhere"


def test_broadcast_reaches_every_client_after_its_snapshot(client: TestClient, hub: Hub) -> None:
    with client.websocket_connect("/ws") as first, client.websocket_connect("/ws") as second:
        for ws in (first, second):
            assert ws.receive_json()["type"] == "snapshot"

        client.portal.call(hub.broadcast, MOVED)

        for ws in (first, second):
            assert ws.receive_json() == MOVED.model_dump(mode="json")


def test_audio_goes_out_as_a_binary_frame(client: TestClient, hub: Hub) -> None:
    chunk = AudioChunk(line_id=6, sequence=0, pcm=b"\x01\x00\x02\x00")

    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        client.portal.call(hub.broadcast, chunk)

        assert AudioChunk.decode(ws.receive_bytes()) == chunk


def test_forgets_clients_that_disconnect(client: TestClient, hub: Hub) -> None:
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        assert len(hub.connections) == 1

    assert hub.connections == set()
    client.portal.call(hub.broadcast, MOVED)


def test_dispatches_client_messages_to_subscribers(client: TestClient, hub: Hub) -> None:
    said: list[PlayerSayMessage] = []
    hub.subscribe(PlayerSayMessage, said.append)
    hub.subscribe(
        PlayerMoveMessage,
        lambda move: hub.broadcast(EntityMovedMessage(entity_id="player", position=move.position)),
    )

    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "player_say", "text": "Hi Mei", "target": "mei"})
        ws.send_json({"type": "player_move", "position": {"x": 3, "y": 4}})

        assert ws.receive_json()["position"] == {"x": 3, "y": 4}

    assert said == [PlayerSayMessage(text="Hi Mei", target="mei")]


def test_ignores_bad_client_frames(
    client: TestClient, hub: Hub, caplog: pytest.LogCaptureFixture
) -> None:
    hub.subscribe(PlayerMoveMessage, lambda move: hub.broadcast(MOVED))
    hub.subscribe(PlayerMoveMessage, lambda move: 1 / 0)

    with caplog.at_level(logging.WARNING), client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_text("not json")
        ws.send_json({"type": "teleport"})
        ws.send_bytes(b"\x00")
        ws.send_json({"type": "player_move", "position": {"x": 3, "y": 4}})

        assert ws.receive_json() == MOVED.model_dump(mode="json")

    assert [r.levelname for r in caplog.records] == ["WARNING"] * 3 + ["ERROR"]


def test_unsubscribe(client: TestClient, hub: Hub) -> None:
    said: list[PlayerSayMessage] = []
    unsubscribe = hub.subscribe(PlayerSayMessage, said.append)
    hub.subscribe(PlayerMoveMessage, lambda move: hub.broadcast(MOVED))
    unsubscribe()
    unsubscribe()

    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "player_say", "text": "Hi", "target": "mei"})
        ws.send_json({"type": "player_move", "position": {"x": 3, "y": 4}})
        ws.receive_json()

    assert said == []
