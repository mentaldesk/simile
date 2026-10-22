import time
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.app import create_app
from simile.economy import PLAYER, Kind
from simile.economy.economy import economy_of
from simile.persistence import player_of
from simile.player.config import SALVAGE
from simile.schema import (
    PLAYER_ID,
    Item,
    ItemKind,
    Location,
    LocationKind,
    Tile,
    TileArea,
)
from simile.sim import Clock, World, world_of
from simile.world import Movement, Point, movement_of
from simile.world.map import Pickup, PickupKind, load_maps

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


def test_hunger_rises_only_while_a_client_is_in_the_game(make_package: MakePackage) -> None:
    app = make_app(make_package)

    with TestClient(app) as client:
        player = player_of(app)

        def rise() -> float:
            before = player.hunger
            for _ in range(10):
                client.portal.call(world_of(app).loop.tick)
            return player.hunger - before

        with client.websocket_connect("/ws") as menu:
            next_of(menu, "player_state")
            on_the_menu = rise()
            with client.websocket_connect("/ws") as game:
                next_of(game, "player_state")
                connected = rise()
                move(client, app, game, 12, 15, "kapok_walk")
                playing = rise()
            left = rise()

    assert on_the_menu == connected == left == 0
    assert playing == pytest.approx(0.25 / 3600)


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
        client.portal.call(lambda: setattr(player, "items", [*player.items, BUN]))
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
    assert [item["id"] for item in woken["player"]["items"]] == ["lamp"]
    assert woken["player"]["left"] == [
        {"at": {"map": "kapok_walk", "x": 12, "y": 15}, "items": [BUN.model_dump(mode="json")]}
    ]
    assert woken["meal"] == HOME
    assert [item["id"] for item in picked_up["player"]["items"]] == ["lamp", "pork_bun"]
    assert "left" not in picked_up["player"]


def with_salvage_and_a_stall(app: Starlette) -> None:
    maps = load_maps()
    street = maps["kapok_walk"]
    stall = Location(
        id="scrap_stall",
        name="The scrap trader's stall",
        kind=LocationKind.AMENITY,
        map="kapok_walk",
        area=TileArea(x=14, y=13, width=5, height=3),
        entry=Tile(x=18, y=15),
    )
    lying = (
        Pickup("metro_salvage_1", PickupKind.SALVAGE, "kapok_walk", 26, 15),
        Pickup("metro_secret_stairwell", PickupKind.SECRET, "kapok_walk", 30, 15, money=25),
    )
    street = replace(street, locations=(*street.locations, stall), pickups=lying)
    app.state.movement = Movement(maps | {"kapok_walk": street}, world_of(app).bus)


def test_they_pick_up_salvage_and_cash_and_sell_the_salvage_at_the_stall(
    make_package: MakePackage,
) -> None:
    app = make_app(make_package)
    with_salvage_and_a_stall(app)
    wire = SALVAGE["metro_salvage_1"].item.model_dump(mode="json")

    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        greeted = next_of(ws, "player_state")
        move(client, app, ws, 26, 15, "kapok_walk")
        ws.send_json({"type": "pick_up"})
        salvaged = next_of(ws, "player_state")
        move(client, app, ws, 30, 15, "kapok_walk")
        ws.send_json({"type": "pick_up"})
        found = next_of(ws, "player_state")
        move(client, app, ws, 16, 15, "kapok_walk")
        client.portal.call(world_of(app).loop.tick)
        at_the_stall = next_of(ws, "player_state")
        ws.send_json({"type": "sell", "item": None})
        sold = next_of(ws, "player_state")
        economy = economy_of(app)
        ledger = economy.ledger

    assert greeted["piles"] == [
        {"at": {"map": "kapok_walk", "x": 26, "y": 15}, "items": [wire]},
        {"at": {"map": "kapok_walk", "x": 30, "y": 15}, "items": [], "money": 25.0},
    ]
    assert salvaged["player"]["items"][1:] == [wire]
    assert salvaged["player"]["taken"] == {"metro_salvage_1": "2026-01-01T10:00:00Z"}
    assert len(salvaged["piles"]) == 1
    assert found["player"]["money"] == 25
    assert "piles" not in found
    assert at_the_stall["buyer"] == {
        "place": "scrap_stall",
        "name": "The scrap trader's stall",
        "prices": {"copper_wire": 6.0},
    }
    assert [item["id"] for item in sold["player"]["items"]] == ["lamp"]
    assert sold["player"]["money"] == 31
    assert sold["buyer"]["prices"] == {}
    assert [entry.kind for entry in ledger.entries] == [Kind.FOUND, Kind.SALVAGE]
    assert ledger.net(PLAYER) == 31
    assert ledger.gap(economy.money) == pytest.approx(0)
