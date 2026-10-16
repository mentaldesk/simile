from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient
from starlette.testclient import WebSocketTestSession as WebSocket

from simile.app import create_app
from simile.debug import overlay
from simile.sim import Clock, World

MakePackage = Callable[[dict[str, str]], str]

START = datetime(2026, 1, 1, 10, tzinfo=UTC)
LIFESPANS = ("behaviour", "conversation", "llm", "memory", "protocol", "world")


@pytest.fixture
def app(make_package: MakePackage, monkeypatch: pytest.MonkeyPatch) -> Starlette:
    monkeypatch.setattr(overlay, "INTERVAL", 0.05)
    package = make_package(
        {
            f"{module}/lifespan.py": f"from simile.{module}.lifespan import lifespan\n"
            for module in LIFESPANS
        }
        | {
            "debug/lifespan.py": "from simile.debug.lifespan import running\n",
            "sim/lifespan.py": "from simile.sim.lifespan import running\n",
            "protocol/routes.py": "from simile.protocol.routes import routes\n",
        }
    )
    app = create_app(package)
    app.state.world = World(Clock(START, speed=60))
    return app


@pytest.fixture
def ws(app: Starlette) -> Iterator[WebSocket]:
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "snapshot"
        yield ws


def next_state(ws: WebSocket) -> dict[str, Any]:
    while (message := ws.receive_json())["type"] != "npc_state":
        pass
    return message


def test_sends_the_watched_npcs_state_as_it_changes(ws: WebSocket) -> None:
    ws.send_json({"type": "watch_npc", "npc_id": "kofi"})

    first = next_state(ws)
    later = next_state(ws)

    assert first["npc_id"] == later["npc_id"] == "kofi"
    assert first["state"]["name"] == "Kofi Lindqvist-Mensah"
    assert {"goal", "needs", "values", "relationships", "memories", "conversation"} <= set(
        first["state"]
    )
    assert datetime.fromisoformat(later["state"]["time"]) > datetime.fromisoformat(
        first["state"]["time"]
    )


def test_headless_runs_have_no_overlay(make_package: MakePackage) -> None:
    app = create_app(
        make_package({"debug/lifespan.py": "from simile.debug.lifespan import running\n"})
    )
    app.state.headless = True

    with TestClient(app):
        assert not hasattr(app.state, "debug")
