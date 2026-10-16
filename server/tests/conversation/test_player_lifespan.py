from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient, WebSocketTestSession

from simile.app import create_app
from simile.conversation import conversations_of
from simile.llm.lifespan import CANNED
from simile.schema import PLAYER_ID
from simile.sim import Clock, World, world_of

MakePackage = Callable[[dict[str, str]], str]

START = datetime(2026, 1, 1, 10, tzinfo=UTC)
MODULES = ("behaviour", "conversation", "llm", "memory", "protocol", "world")


@pytest.fixture
def app(make_package: MakePackage) -> Starlette:
    package = make_package(
        {
            f"{module}/lifespan.py": f"from simile.{module}.lifespan import lifespan\n"
            for module in MODULES
        }
        | {"protocol/routes.py": "from simile.protocol.routes import routes\n"}
    )
    app = create_app(package)
    app.state.world = World(Clock(START))
    return app


def receive(ws: WebSocketTestSession, kind: str) -> dict[str, Any]:
    while (message := ws.receive_json())["type"] != kind:
        pass
    return message


def test_walk_up_to_an_npc_type_and_see_the_reply(app: Starlette) -> None:
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        kofi = next(e for e in receive(ws, "snapshot")["entities"] if e["id"] == "kofi")
        x, y = kofi["position"]["x"], kofi["position"]["y"]
        ws.send_json({"type": "player_move", "position": {"x": x + 1, "y": y}})
        ws.send_json({"type": "player_say", "text": "Hello!", "target": "kofi"})

        started = receive(ws, "conversation_started")["conversation"]
        said = receive(ws, "line")["line"]
        first = receive(ws, "line")["line"]
        for _ in range(15):
            client.portal.call(world_of(app).loop.tick)
        second = receive(ws, "line")["line"]
        live = client.portal.call(conversations_of(app).live)

    assert started["participants"] == [PLAYER_ID, "kofi"]
    assert (said["speaker"], said["text"]) == (PLAYER_ID, "Hello!")
    hello, question = CANNED[0].split(" ", 1)
    assert (first["speaker"], first["text"]) == ("kofi", hello)
    assert (second["speaker"], second["text"]) == ("kofi", question)
    assert {said["conversation_id"], first["conversation_id"]} == {started["id"]}
    assert [line.text for line in live[0].lines] == ["Hello!", hello, question]
