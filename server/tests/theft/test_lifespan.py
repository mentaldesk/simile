import time
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.app import create_app
from simile.economy import PLAYER, Kind
from simile.economy.economy import economy_of
from simile.memory import memory_of
from simile.persistence import player_of
from simile.schema import PLAYER_ID, MapTile, MemoryKind
from simile.sim import Clock, World, world_of
from simile.street.finds import STASHES
from simile.world import Point, movement_of

MakePackage = Callable[[dict[str, str]], str]

START = datetime(2026, 1, 1, 10, tzinfo=UTC)
LIFESPANS = ("behaviour", "economy", "memory", "protocol", "world")
BED = STASHES["house_9_bed"]


def make_app(make_package: MakePackage) -> Starlette:
    files = {f"{m}/lifespan.py": f"from simile.{m}.lifespan import lifespan\n" for m in LIFESPANS}
    files["protocol/routes.py"] = "from simile.protocol.routes import routes\n"
    files["player/lifespan.py"] = "from simile.player.lifespan import running\n"
    files["theft/lifespan.py"] = "from simile.theft.lifespan import running\n"
    app = create_app(make_package(files))
    app.state.world = World(Clock(START))
    return app


def until(client: TestClient, done: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 2
    while not client.portal.call(done):
        assert time.monotonic() < deadline, "it never happened"
        time.sleep(0.001)


def test_searching_a_house_finds_its_cash_and_whoever_is_in_the_room_sees(
    make_package: MakePackage,
) -> None:
    app = make_app(make_package)
    at = Point(2, 2, "house_9_floor_1")

    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        player, store = player_of(app), memory_of(app)
        client.portal.call(lambda: movement_of(app).place("priya", MapTile(map=at.map, x=4, y=2)))
        ws.send_json({"type": "player_move", "position": {"x": at.x, "y": at.y, "map": at.map}})
        until(client, lambda: movement_of(app).entities().get(PLAYER_ID) == at)
        ws.send_json({"type": "pick_up"})
        until(client, lambda: BED.id in player.searched)
        money = player.money
        client.portal.call(world_of(app).loop.tick)
        seen = store.recall("priya", START, about=PLAYER_ID, kind=MemoryKind.OBSERVATION, k=10)
        ledger = economy_of(app).ledger

    assert money == BED.money
    assert [(entry.kind, entry.place) for entry in ledger.entries] == [(Kind.FOUND, BED.id)]
    assert ledger.net(PLAYER) == pytest.approx(BED.money)
    assert [memory.content for memory in seen] == [
        "I saw Visitor going through the bedside drawer in my house."
    ]
