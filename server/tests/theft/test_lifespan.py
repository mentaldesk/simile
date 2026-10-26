import time
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.app import create_app
from simile.economy import PLAYER, Kind
from simile.economy.economy import economy_of
from simile.persistence import player_of
from simile.schema import PLAYER_ID
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


def test_searching_a_house_finds_its_cash_through_the_ledger(make_package: MakePackage) -> None:
    app = make_app(make_package)
    at = Point(2, 2, "house_9_floor_1")

    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        player = player_of(app)
        ws.send_json({"type": "player_move", "position": {"x": at.x, "y": at.y, "map": at.map}})
        until(client, lambda: movement_of(app).entities().get(PLAYER_ID) == at)
        ws.send_json({"type": "pick_up"})
        until(client, lambda: BED.id in player.searched)
        unpaid = player.money
        client.portal.call(world_of(app).loop.tick)
        ledger = economy_of(app).ledger

    assert (unpaid, player.money) == (0, BED.money)
    assert [(entry.kind, entry.place) for entry in ledger.entries] == [(Kind.FOUND, BED.id)]
    assert ledger.net(PLAYER) == pytest.approx(BED.money)
