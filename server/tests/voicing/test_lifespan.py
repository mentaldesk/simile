import json
import sys
import time
import types
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient, WebSocketTestSession

from simile.app import create_app
from simile.conversation import conversations_of
from simile.npc import load_npcs
from simile.protocol import AudioChunk, LineMessage, hub_of
from simile.protocol.hub import Outgoing
from simile.sim import Clock, World, world_of
from simile.voice import FakeSynthesiser
from simile.world import Point, movement_of

MakePackage = Callable[[dict[str, str]], str]

START = datetime(2026, 1, 1, 10, tzinfo=UTC)
LIFESPANS = ("behaviour", "conversation", "llm", "memory", "protocol", "voice", "voicing", "world")

type Frame = dict[str, Any] | AudioChunk


@pytest.fixture
def qwen(monkeypatch: pytest.MonkeyPatch, synthesiser: FakeSynthesiser) -> FakeSynthesiser:
    module = types.ModuleType("simile.voice.qwen")
    module.QwenSynthesiser = lambda: synthesiser  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "simile.voice.qwen", module)
    monkeypatch.setenv("SIMILE_VOICE", "1")
    return synthesiser


@pytest.fixture
def app(make_package: MakePackage, qwen: FakeSynthesiser) -> Starlette:
    package = make_package(
        {
            f"{module}/lifespan.py": f"from simile.{module}.lifespan import *  # noqa: F403\n"
            for module in LIFESPANS
        }
        | {"protocol/routes.py": "from simile.protocol.routes import routes\n"}
    )
    app = create_app(package)
    app.state.world = World(Clock(START))
    return app


def frames(ws: WebSocketTestSession) -> Iterator[Frame]:
    while True:
        message = ws.receive()
        if message.get("bytes") is not None:
            yield AudioChunk.decode(message["bytes"])
        else:
            yield json.loads(message["text"])


def next_line(received: Iterator[Frame], speaker: str) -> dict[str, Any]:
    return next(
        frame
        for frame in received
        if isinstance(frame, dict)
        and frame["type"] == "line"
        and frame["line"]["speaker"] == speaker
    )


def audio_of(received: Iterator[Frame], line_id: int) -> list[AudioChunk]:
    chunks = []
    for frame in received:
        if isinstance(frame, AudioChunk) and frame.line_id == line_id:
            chunks.append(frame)
            if frame.last:
                return chunks
    raise AssertionError("unreachable")


def stand_by(ws: WebSocketTestSession, received: Iterator[Frame], npc: str, dx: float) -> None:
    snapshot = next(f for f in received if isinstance(f, dict) and f["type"] == "snapshot")
    position = next(e for e in snapshot["entities"] if e["id"] == npc)["position"]
    ws.send_json({"type": "player_move", "position": position | {"x": position["x"] + dx}})


def test_registers_every_npc_voice_at_startup(qwen: FakeSynthesiser) -> None:
    app = create_app()

    with TestClient(app):
        assert callable(app.state.voiced)
        assert conversations_of(app).audio is not None

    voiced = {npc.id for npc in load_npcs() if npc.voice.reference_clip}
    assert voiced
    assert set(qwen.voices) == voiced
    assert not hasattr(app.state, "voiced")
    assert conversations_of(app).audio is None


def test_does_nothing_unvoiced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SIMILE_VOICE", raising=False)
    app = create_app()

    with TestClient(app):
        assert not hasattr(app.state, "voiced")


def test_the_player_hears_the_reply_after_its_line(app: Starlette, qwen: FakeSynthesiser) -> None:
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        received = frames(ws)
        stand_by(ws, received, "kofi", 1)
        ws.send_json({"type": "player_say", "text": "Hello!", "target": "kofi"})

        said = next_line(received, "player")
        reply = next_line(received, "kofi")
        chunks = audio_of(received, reply["line"]["id"])

    assert not said["voiced"]
    assert reply["voiced"]
    assert [chunk.pcm for chunk in chunks[:-1]] == [qwen.chunk(i) for i in range(qwen.chunks)]
    assert chunks[-1].last


def test_overhears_npcs_only_within_earshot(app: Starlette, qwen: FakeSynthesiser) -> None:
    hub, sent = hub_of(app), list[Outgoing]()
    broadcast = hub.broadcast

    def record(message: Outgoing) -> None:
        sent.append(message)
        broadcast(message)

    hub.broadcast = record  # type: ignore[method-assign]

    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        movement = movement_of(app)

        def move_player(x: float, y: float, map: str) -> None:
            ws.send_json({"type": "player_move", "position": {"x": x, "y": y, "map": map}})
            wait_for(lambda: movement.entities().get("player") == Point(x, y, map))

        def next_spoken(conversation: str) -> LineMessage:
            def said() -> list[LineMessage]:
                return [
                    m
                    for m in sent
                    if isinstance(m, LineMessage) and m.line.conversation_id == conversation
                ]

            before = len(said())
            for _ in range(1000):
                client.portal.call(world_of(app).loop.tick)
                if len(said()) > before:
                    return said()[-1]
            raise AssertionError("nobody spoke")

        kofi = client.portal.call(movement.position, "kofi")
        move_player(kofi.x + 2, kofi.y, kofi.map)
        talk = client.portal.call(conversations_of(app).start, "kofi", "priya")
        near = next_spoken(talk.id)
        wait_for(lambda: any(c.last for c in sent if isinstance(c, AudioChunk)))
        move_player(kofi.x + 100, kofi.y, kofi.map)
        far = next_spoken(talk.id)

    assert near.voiced
    audio = [c.line_id for c in sent if isinstance(c, AudioChunk)]
    assert audio == [near.line.id] * (qwen.chunks + 1)
    assert not far.voiced


def wait_for(condition: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 2
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.001)
