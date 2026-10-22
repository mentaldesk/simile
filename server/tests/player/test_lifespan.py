import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.app import create_app
from simile.persistence import player_of
from simile.schema import PLAYER_ID, Item, ItemKind
from simile.sim import Clock, World, world_of
from simile.world import Point, movement_of

MakePackage = Callable[[dict[str, str]], str]

START = datetime(2026, 1, 1, 10, tzinfo=UTC)
LIFESPANS = ("behaviour", "economy", "memory", "protocol", "world")
HOME = {"place": "maker_space", "name": "home", "price": 0.0}
BUN = Item(id="pork_bun", kind=ItemKind.FOOD, name="Pork bun", weight=0.2)


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


def test_new_clients_get_the_players_state_after_the_snapshot_and_clock(
    make_package: MakePackage,
) -> None:
    app = make_app(make_package)

    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        greeted = [ws.receive_json() for _ in range(3)]

    assert [message["type"] for message in greeted] == ["snapshot", "clock", "player_state"]
    assert greeted[2]["player"]["hunger"] == 0
    assert "meal" not in greeted[2]


def test_the_player_eats_at_home_and_from_what_they_carry(make_package: MakePackage) -> None:
    app = make_app(make_package)

    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        tick = world_of(app).loop.tick
        player = player_of(app)
        next_of(ws, "player_state")
        move(client, app, ws, 13, 2, "maker_space_floor_0")
        client.portal.call(tick)
        at_home = next_of(ws, "player_state")

        client.portal.call(lambda: setattr(player, "hunger", 0.9))
        client.portal.call(tick)
        next_of(ws, "player_state")
        ws.send_json({"type": "eat", "item": None})
        fed = next_of(ws, "player_state")

        client.portal.call(lambda: setattr(player, "items", [BUN]))
        client.portal.call(lambda: setattr(player, "hunger", 0.5))
        client.portal.call(tick)
        next_of(ws, "player_state")
        ws.send_json({"type": "eat", "item": "pork_bun"})
        snacked = next_of(ws, "player_state")

    assert at_home["meal"] == HOME
    assert fed["player"]["hunger"] == 0
    assert snacked["player"]["items"] == []
    assert snacked["player"]["hunger"] < 0.5


def test_starving_wakes_them_at_home_and_they_pick_up_what_they_left(
    make_package: MakePackage,
) -> None:
    app = make_app(make_package)

    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        tick = world_of(app).loop.tick
        player = player_of(app)
        move(client, app, ws, 12, 15, "kapok_walk")
        client.portal.call(lambda: setattr(player, "hunger", 1 - 1e-9))
        client.portal.call(tick)
        collapsed = next_of(ws, "player_collapsed")
        woken = next_of(ws, "player_state")
        home = client.portal.call(movement_of(app).position, PLAYER_ID)

        move(client, app, ws, 12, 15, "kapok_walk")
        ws.send_json({"type": "pick_up"})
        picked_up = next_of(ws, "player_state")

    assert collapsed["position"] == {"x": 13, "y": 2, "map": "maker_space_floor_0"}
    assert home == Point(13, 2, "maker_space_floor_0")
    assert woken["player"]["hunger"] == 0.75
    assert woken["player"]["items"] == []
    assert woken["player"]["left"] == [
        {"at": {"map": "kapok_walk", "x": 12, "y": 15}, "items": [picked_up["player"]["items"][0]]}
    ]
    assert woken["meal"] == HOME
    assert picked_up["player"]["items"][0]["id"] == "lamp"
    assert "left" not in picked_up["player"]
