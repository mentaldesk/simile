import asyncio
import random
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.app import create_app
from simile.economy import PLAYER, Kind
from simile.economy.economy import economy_of
from simile.npc import load_npcs
from simile.persistence import investigation_of, player_of
from simile.player.config import SALVAGE
from simile.schema import PLAYER_ID, Bionic, Body, Item, ItemKind
from simile.sim import Clock, World, world_of
from simile.story import make_incident
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


def test_on_the_metro_they_pick_up_salvage_and_cash_and_sell_the_salvage_at_the_stall(
    make_package: MakePackage,
) -> None:
    app = make_app(make_package)
    wire = SALVAGE["metro_salvage_1"].item.model_dump(mode="json")

    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        greeted = next_of(ws, "player_state")
        move(client, app, ws, 38, 12, "metro")
        ws.send_json({"type": "pick_up"})
        salvaged = next_of(ws, "player_state")
        move(client, app, ws, 52, 10, "metro")
        ws.send_json({"type": "pick_up"})
        found = next_of(ws, "player_state")
        move(client, app, ws, 26, 15, "metro")
        client.portal.call(world_of(app).loop.tick)
        at_the_stall = next_of(ws, "player_state")
        ws.send_json({"type": "sell", "item": None})
        sold = next_of(ws, "player_state")
        economy = economy_of(app)
        ledger = economy.ledger

    assert len(metro(greeted["piles"])) == 20
    assert {"at": {"map": "metro", "x": 38, "y": 12}, "items": [wire]} in greeted["piles"]
    assert salvaged["player"]["items"][1:] == [wire]
    assert salvaged["player"]["taken"] == {"metro_salvage_1": "2026-01-01T10:00:00Z"}
    assert len(metro(salvaged["piles"])) == 19
    assert found["player"]["money"] == 40
    assert len(metro(found["piles"])) == 18
    assert at_the_stall["buyer"] == {
        "place": "scrap_stall",
        "name": "The scrap trader's stall",
        "prices": {"copper_wire": 6.0},
    }
    assert [item["id"] for item in sold["player"]["items"]] == ["lamp"]
    assert sold["player"]["money"] == 46
    assert sold["buyer"]["prices"] == {}
    assert [entry.kind for entry in ledger.entries] == [Kind.FOUND, Kind.SALVAGE]
    assert ledger.net(PLAYER) == 46
    assert ledger.gap(economy.money) == pytest.approx(0)


@pytest.mark.parametrize("datajack", [False, True], ids=["without", "with the datajack"])
def test_e_at_the_dead_terminal_finds_its_clue_only_with_the_datajack(
    make_package: MakePackage, datajack: bool
) -> None:
    app = make_app(make_package)
    made = asyncio.run(make_incident(load_npcs(), START, None, rng=random.Random(1)))
    investigation_of(app).incident = made.incident
    if datajack:
        player_of(app).body = Body(vertebra=Bionic.DATAJACK)

    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        next_of(ws, "player_state")
        move(client, app, ws, 104, 15, "metro")
        ws.send_json({"type": "pick_up"})
        journal = next_of(ws, "journal") if datajack else None
        ws.send_json({"type": "lamp", "on": True})
        next_of(ws, "player_state")
        entries = investigation_of(app).journal

    assert [entry.fact_id for entry in entries] == (["lift_log"] if datajack else [])
    if journal is not None:
        [entry] = journal["entries"]
        assert entry["source"] == {"kind": "clue", "id": "metro_terminal", "name": "Dead terminal"}
        assert "maker's mark" in entry["text"] and entry["flushed"] is None


def test_a_part_sold_at_the_stall_is_bought_back_with_buy(make_package: MakePackage) -> None:
    app = make_app(make_package)
    plug = Item(id="usb_c_connector", kind=ItemKind.PART, name="USB-C connector", weight=0.1)
    player_of(app).items = [plug]
    player_of(app).money = 20

    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        next_of(ws, "player_state")
        move(client, app, ws, 26, 15, "metro")
        client.portal.call(world_of(app).loop.tick)
        next_of(ws, "player_state")
        ws.send_json({"type": "sell", "item": None})
        sold = next_of(ws, "player_state")
        ws.send_json({"type": "buy", "item": "usb_c_connector"})
        bought = next_of(ws, "player_state")

    offer = {"item": plug.model_dump(mode="json"), "price": 24.0}
    assert sold["buyer"]["stock"] == [offer]
    assert sold["player"]["sales"] == [{**offer, "place": "scrap_stall", "price": 12.0}]
    assert bought["player"]["items"] == [plug.model_dump(mode="json")]
    assert bought["player"]["money"] == 8
    assert "stock" not in bought["buyer"]
    assert "sales" not in bought["player"]


def test_e_at_aris_bench_teaches_the_datajack(
    make_package: MakePackage,
) -> None:
    files = {f"{m}/lifespan.py": f"from simile.{m}.lifespan import lifespan\n" for m in LIFESPANS}
    files["protocol/routes.py"] = "from simile.protocol.routes import routes\n"
    files["player/lifespan.py"] = "from simile.player.lifespan import running\n"
    files["clinic/lifespan.py"] = "from simile.clinic.lifespan import lifespan\n"
    app = create_app(make_package(files))
    app.state.world = World(Clock(START))

    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        next_of(ws, "player_state")
        move(client, app, ws, 5, 2, "maker_space_floor_0")
        ws.send_json({"type": "pick_up"})
        searched = next_of(ws, "player_state")
        while "searched" not in searched["player"]:
            searched = next_of(ws, "player_state")

    assert searched["player"]["searched"] == ["maker_space_bench"]
    assert searched["player"]["mind"] == {"recipes": ["datajack"]}
    assert [recipe["bionic"] for recipe in searched["recipes"]] == ["datajack"]


def metro(piles: list[dict]) -> list[dict]:
    return [pile for pile in piles if pile["at"]["map"] == "metro"]
