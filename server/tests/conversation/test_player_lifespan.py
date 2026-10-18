from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient, WebSocketTestSession

from simile.app import create_app
from simile.conversation import conversations_of
from simile.conversation.player import PlayerConversations
from simile.llm import FakeProvider, LLMClient
from simile.llm.lifespan import CANNED
from simile.memory import memory_of
from simile.news import news_of
from simile.schema import PLAYER_ID, CoreValue, Memory, MemoryKind, NewsItem
from simile.sim import Clock, World, world_of

MakePackage = Callable[[dict[str, str]], str]

START = datetime(2026, 1, 1, 10, tzinfo=UTC)
MODULES = ("behaviour", "conversation", "llm", "memory", "protocol", "world")


def make_app(make_package: MakePackage, *modules: str) -> Starlette:
    package = make_package(
        {
            f"{module}/lifespan.py": f"from simile.{module}.lifespan import lifespan\n"
            for module in modules
        }
        | {"protocol/routes.py": "from simile.protocol.routes import routes\n"}
    )
    app = create_app(package)
    app.state.world = World(Clock(START))
    return app


@pytest.fixture
def app(make_package: MakePackage) -> Starlette:
    return make_app(make_package, *MODULES)


def receive(ws: WebSocketTestSession, kind: str) -> dict[str, Any]:
    while (message := ws.receive_json())["type"] != kind:
        pass
    return message


def test_the_player_conversations_are_on_the_app_while_it_runs(app: Starlette) -> None:
    with TestClient(app):
        players = app.state.players
        assert isinstance(players, PlayerConversations)
        assert conversations_of(app).player_request == players.request

    assert not hasattr(app.state, "players")


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


def test_a_reply_recalls_an_article_by_its_stored_tags_and_summary(
    make_package: MakePackage,
) -> None:
    app = make_app(make_package, *MODULES, "news")
    rover = NewsItem(
        id="rover",
        title="Mission to the red planet",
        url="https://example.com/rover",
        summary="Engineers test a new rover in the desert.",
        published=START - timedelta(hours=2),
        values={value: 0.1 for value in CoreValue},
        tags=["space exploration", "robots"],
    )
    take = 'I read "Mission to the red planet" on the news terminal. Wild.'
    news_of(app).add([rover])
    memory_of(app).add(
        Memory(
            owner="kofi",
            kind=MemoryKind.NEWS,
            content=take,
            salience=0.6,
            valence=0.5,
            timestamp=START - timedelta(hours=1),
            news_id="rover",
        )
    )
    provider = FakeProvider(default="Robots in the desert! [values: adventure]")

    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        app.state.llm = LLMClient(provider)
        kofi = next(e for e in receive(ws, "snapshot")["entities"] if e["id"] == "kofi")
        x, y = kofi["position"]["x"], kofi["position"]["y"]
        ws.send_json({"type": "player_move", "position": {"x": x + 1, "y": y}})
        ws.send_json({"type": "player_say", "text": "Robots out in the desert!", "target": "kofi"})
        receive(ws, "line")
        receive(ws, "line")

    prompt = provider.requests[0].messages[-1].content
    assert f"You read about what Visitor just mentioned:\n- {take}" in prompt
