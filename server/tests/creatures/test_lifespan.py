import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.app import create_app
from simile.creatures.engine import creatures_of
from simile.creatures.kind import Kind
from simile.creatures.ways import Chase
from simile.persistence import player_of
from simile.schema import PLAYER_ID, CreatureKind, EffectKind, MapTile
from simile.sim import Clock, World, world_of
from simile.world import Point, movement_of

MakePackage = Callable[[dict[str, str]], str]

START = datetime(2026, 1, 1, 10, tzinfo=UTC)
LIFESPANS = ("behaviour", "creatures", "economy", "memory", "protocol", "world")
RAT = Kind(CreatureKind.RAT, ways=(Chase(sight=6),), bites=True)


def make_app(make_package: MakePackage) -> Starlette:
    files = {f"{m}/lifespan.py": f"from simile.{m}.lifespan import lifespan\n" for m in LIFESPANS}
    files["protocol/routes.py"] = "from simile.protocol.routes import routes\n"
    files["player/lifespan.py"] = "from simile.player.lifespan import running\n"
    app = create_app(make_package(files))
    app.state.world = World(Clock(START))
    return app


def next_of(ws: Any, type: str) -> dict[str, Any]:
    for _ in range(500):
        if (message := ws.receive_json())["type"] == type:
            return message
    raise AssertionError(f"no {type}")


def move(client: TestClient, app: Starlette, ws: Any, x: float, y: float, map: str) -> None:
    ws.send_json({"type": "player_move", "position": {"x": x, "y": y, "map": map}})
    movement, deadline = movement_of(app), time.monotonic() + 2
    while client.portal.call(movement.entities).get(PLAYER_ID) != Point(x, y, map):
        assert time.monotonic() < deadline, "the server never had the player there"
        time.sleep(0.001)


def test_the_snapshot_has_the_creatures(
    make_package: MakePackage,
) -> None:
    app = make_app(make_package)

    with TestClient(app) as client:
        at = MapTile(map="metro", x=66, y=15)
        rat = client.portal.call(lambda: creatures_of(app).spawn(Kind(CreatureKind.RAT), at))
        with client.websocket_connect("/ws") as ws:
            snapshot = next_of(ws, "snapshot")

    assert snapshot["creatures"] == [
        {
            "id": rat.id,
            "kind": "rat",
            "position": {"x": 66.0, "y": 15.0, "map": "metro"},
            "facing": "east",
            "state": "idle",
        }
    ]


def test_a_rat_in_reach_bites_the_player_in_the_game_and_its_moves_reach_the_client(
    make_package: MakePackage,
) -> None:
    app = make_app(make_package)

    with TestClient(app) as client:
        client.portal.call(lambda: creatures_of(app).spawn(RAT, MapTile(map="metro", x=62, y=15)))
        player = player_of(app)

        def tick(seconds: float) -> None:
            for _ in range(round(seconds / 0.1)):
                client.portal.call(world_of(app).loop.tick)

        tick(2)
        assert player.health == 1, "nobody's in the game"
        with client.websocket_connect("/ws") as ws:
            move(client, app, ws, 65, 15, "metro")
            tick(3)
            moved = next_of(ws, "creature_moved")

    assert moved["creature"]["state"] == "chasing"
    assert player.health < 1
    assert [effect.kind for effect in player.effects] == [EffectKind.RAT_BITE]
