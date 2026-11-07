import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.app import create_app
from simile.clinic.config import DEFAULT_CONFIG
from simile.clinic.doctor import DOCTOR
from simile.economy import OUTSIDE, PILES, PLAYER, Kind
from simile.economy.economy import economy_of
from simile.persistence import player_of
from simile.player.health import health_of
from simile.protocol import Vital
from simile.schema import (
    PLAYER_ID,
    Bionic,
    Body,
    Effect,
    EffectKind,
    Item,
    ItemKind,
    Mind,
    Player,
    lamp,
)
from simile.sim import Clock, World, world_of
from simile.world import Point, movement_of

MakePackage = Callable[[dict[str, str]], str]

START = datetime(2026, 1, 1, 10, tzinfo=UTC)
LIFESPANS = ("behaviour", "economy", "memory", "protocol", "world")
CLINIC = Point(4, 2, "clinic_floor_0")
CELL_PARTS = [
    id for id, n in DEFAULT_CONFIG.recipes[Bionic.POWER_CELL].parts.items() for _ in range(n)
]


def make_app(make_package: MakePackage) -> Starlette:
    files = {f"{m}/lifespan.py": f"from simile.{m}.lifespan import lifespan\n" for m in LIFESPANS}
    files["protocol/routes.py"] = "from simile.protocol.routes import routes\n"
    files["player/lifespan.py"] = "from simile.player.lifespan import running\n"
    files["clinic/lifespan.py"] = "from simile.clinic.lifespan import lifespan, running\n"
    app = create_app(make_package(files))
    app.state.world = World(Clock(START))
    return app


def next_of(ws: Any, type: str) -> dict[str, Any]:
    for _ in range(500):
        if (message := ws.receive_json())["type"] == type:
            return message
    raise AssertionError(f"no {type}")


def until(client: TestClient, done: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 2
    while not client.portal.call(done):
        assert time.monotonic() < deadline, "the server never got there"
        time.sleep(0.001)


def test_the_doctor_stands_in_the_clinic(make_package: MakePackage) -> None:
    app = make_app(make_package)

    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        snapshot = next_of(ws, "snapshot")

    [doctor] = [entity for entity in snapshot["entities"] if entity["id"] == DOCTOR]
    assert doctor == {
        "id": DOCTOR,
        "kind": "npc",
        "name": "Annelie Joubert",
        "position": {"x": 6.0, "y": 2.0, "map": "clinic_floor_0"},
        "pose": "standing",
        "facing": "south",
    }


def test_the_player_sells_a_kidney_and_is_fitted_with_the_cell(make_package: MakePackage) -> None:
    app = make_app(make_package)
    cell = [Item(id=id, kind=ItemKind.PART, name=id, weight=0.1) for id in CELL_PARTS]

    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        next_of(ws, "player_state")
        player, tick = player_of(app), world_of(app).loop.tick
        player.items = [*player.items, *cell]
        ws.send_json({"type": "player_move", "position": {"x": 4, "y": 2, "map": CLINIC.map}})
        until(client, lambda: movement_of(app).entities().get(PLAYER_ID) == CLINIC)
        client.portal.call(tick)
        at_the_clinic = next_of(ws, "player_state")
        ws.send_json({"type": "fit", "bionic": "power_cell", "part": "stomach"})
        ws.send_json({"type": "sell_part", "part": "left_kidney"})
        until(client, lambda: player.money == 100)
        client.portal.call(tick)
        sold = next_of(ws, "player_state")
        ws.send_json({"type": "fit", "bionic": "power_cell", "part": "stomach"})
        until(client, lambda: player.money == 0)
        client.portal.call(tick)
        fitted = next_of(ws, "player_state")
        economy = economy_of(app)

    assert at_the_clinic["buyer"]["parts"] == {"left_kidney": 100.0}
    assert [f["bionic"] for f in at_the_clinic["buyer"]["fittings"]] == ["power_cell"]
    assert sold["player"]["body"]["left_kidney"] == "sold"
    assert "parts" not in sold["buyer"]
    assert fitted["player"]["body"]["stomach"] == "power_cell"
    assert fitted["player"]["money"] == 0
    assert "fittings" not in fitted["buyer"]
    entries = [(e.kind, e.payer, e.payee, e.amount) for e in economy.ledger.entries]
    assert entries == [
        (Kind.SALVAGE, OUTSIDE, PLAYER, 100),
        (Kind.PURCHASE, PLAYER, OUTSIDE, 100),
    ]
    assert economy.ledger.net(PLAYER) == 0
    assert economy.ledger.gap(economy.money) == pytest.approx(0)
    assert Player.model_validate(fitted["player"]).humanity < 1


def test_take_goes_through_a_death_a_partial_take_a_reload_and_the_last_take(
    make_package: MakePackage,
) -> None:
    wire = Item(id="copper_wire", kind=ItemKind.SALVAGE, name="Copper wire", weight=1.5)
    steel = Item(id="scrap_steel", kind=ItemKind.SALVAGE, name="Scrap steel", weight=13.0)
    app = make_app(make_package)
    start = player_of(app)
    start.money = 40.0
    start.items = [*start.items, wire, steel]
    start.body = Body(vertebra=Bionic.DATAJACK)
    move = {"type": "player_move", "position": {"x": 4, "y": 2, "map": CLINIC.map}}
    take: dict[str, object] = {
        "type": "take",
        "corpse": "corpse_1",
        "pile": None,
        "item": None,
        "index": None,
        "bionic": None,
    }

    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        next_of(ws, "player_state")
        player = player_of(app)
        ws.send_json(move)
        until(client, lambda: movement_of(app).entities().get(PLAYER_ID) == CLINIC)
        client.portal.call(health_of(app).hurt, 1.0, Vital.HEALTH)
        client.portal.call(world_of(app).loop.tick)
        next_of(ws, "player_died")
        dead = next_of(ws, "player_state")
        ws.send_json(move)
        until(client, lambda: movement_of(app).entities().get(PLAYER_ID) == CLINIC)
        ws.send_json(take | {"item": "copper_wire", "index": 0})
        partial = next_of(ws, "player_state")
        ws.send_json(take | {"item": "scrap_steel", "index": 0})
        ws.send_json(take | {"bionic": "datajack"})
        jack = next_of(ws, "player_state")
        saved = player.model_dump_json()

    assert dead["player"]["bodies"] == 1
    assert dead["bionics"][0]["weight"] == 0.5
    [corpse] = dead["player"]["corpses"]
    assert (corpse["money"], corpse["bionics"]) == (40, ["datajack"])
    assert [item["id"] for item in partial["player"]["items"]] == ["lamp", "copper_wire"]
    assert [item["id"] for item in jack["player"]["items"]] == ["lamp", "copper_wire", "datajack"]
    assert [item["id"] for item in jack["player"]["corpses"][0]["items"]] == ["scrap_steel"]

    again = make_app(make_package)
    again.state.player = Player.model_validate_json(saved)
    again.state.player.items = [lamp()]

    with TestClient(again) as client, client.websocket_connect("/ws") as ws:
        loaded = next_of(ws, "player_state")
        ws.send_json(move)
        until(client, lambda: movement_of(again).entities().get(PLAYER_ID) == CLINIC)
        ws.send_json(take)
        ws.send_json(take | {"item": "scrap_steel", "index": 0})
        ws.send_json(take | {"corpse": "corpse_9"})
        until(client, lambda: not player_of(again).corpses)
        client.portal.call(world_of(again).loop.tick)
        gone = next_of(ws, "player_state")
        while "corpses" in gone["player"]:
            client.portal.call(world_of(again).loop.tick)
            gone = next_of(ws, "player_state")
        client.portal.call(health_of(again).hurt, 1.0, Vital.HEALTH)
        client.portal.call(world_of(again).loop.tick)
        next_of(ws, "player_died")
        reborn = next_of(ws, "player_state")

    assert loaded["player"]["corpses"][0]["money"] == 40
    assert gone["player"]["money"] == 40
    assert gone["player"]["bodies"] == 1
    assert "bionics" not in gone
    assert reborn["player"]["corpses"][0]["id"] == "corpse_2"


def test_dying_salvaging_and_refitting_gives_a_bionic_back_at_its_grade(
    make_package: MakePackage,
) -> None:
    app = make_app(make_package)
    cell, legs = Bionic.POWER_CELL_2, Bionic.BIONIC_LEGS_2
    start = player_of(app)
    start.money = 150.0
    start.body = Body(stomach=cell, legs=legs)
    start.mind = Mind(recipes=[cell, legs])
    move = {"type": "player_move", "position": {"x": 4, "y": 2, "map": CLINIC.map}}

    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        next_of(ws, "player_state")
        player, tick = player_of(app), world_of(app).loop.tick
        ws.send_json(move)
        until(client, lambda: movement_of(app).entities().get(PLAYER_ID) == CLINIC)
        client.portal.call(health_of(app).hurt, 1.0, Vital.HEALTH)
        client.portal.call(tick)
        next_of(ws, "player_died")
        dead = next_of(ws, "player_state")
        ws.send_json(move)
        until(client, lambda: movement_of(app).entities().get(PLAYER_ID) == CLINIC)
        for bionic in (None, cell.value, legs.value):
            take = {"type": "take", "corpse": "corpse_1", "pile": None, "item": None, "index": None}
            ws.send_json(take | {"bionic": bionic})
        until(client, lambda: not player.corpses)
        salvaged = next_of(ws, "player_state")
        while "corpses" in salvaged["player"] or "fittings" not in salvaged["buyer"]:
            client.portal.call(tick)
            salvaged = next_of(ws, "player_state")
        ws.send_json({"type": "fit", "bionic": "bionic_legs_2", "part": "legs"})
        ws.send_json({"type": "fit", "bionic": "power_cell_2", "part": "stomach"})
        ws.send_json({"type": "fit", "bionic": "bionic_legs_2", "part": "legs"})
        until(client, lambda: player.money == 150 - 63 - 75)
        client.portal.call(tick)
        fitted = next_of(ws, "player_state")
        while "stomach" not in fitted["player"]["body"]:
            client.portal.call(tick)
            fitted = next_of(ws, "player_state")
        economy = economy_of(app)

    assert "stomach" not in dead["player"]["body"]
    [corpse] = dead["player"]["corpses"]
    assert corpse["money"] == 150
    assert sorted(corpse["bionics"]) == ["bionic_legs_2", "power_cell_2"]
    assert {part["id"]: part["weight"] for part in dead["bionics"]} == {
        "bionic_legs_2": 7.0,
        "power_cell_2": 3.0,
    }
    taken = [item for item in salvaged["player"]["items"] if item["kind"] == "bionic"]
    assert sorted(item["bionic"] for item in taken) == ["bionic_legs_2", "power_cell_2"]
    assert "corpses" not in salvaged["player"]
    assert "bionics" not in salvaged
    fittings = {f["bionic"]: f for f in salvaged["buyer"]["fittings"]}
    assert fittings["power_cell_2"]["price"] == 63
    assert fittings["bionic_legs_2"]["price"] == 75
    assert fittings["bionic_legs_2"]["blocked"] == "Needs a power cell first."
    assert fitted["player"]["body"]["stomach"] == "power_cell_2"
    assert fitted["player"]["body"]["legs"] == "bionic_legs_2"
    assert [item["id"] for item in fitted["player"]["items"]] == ["lamp"]
    entries = [(e.kind, e.payer, e.payee, e.amount) for e in economy.ledger.entries]
    assert entries == [
        (Kind.DROPPED, PLAYER, PILES, 150),
        (Kind.RECOVERED, PILES, PLAYER, 150),
        (Kind.PURCHASE, PLAYER, OUTSIDE, 63),
        (Kind.PURCHASE, PLAYER, OUTSIDE, 75),
    ]
    assert economy.ledger.gap(economy.money) == pytest.approx(0)


def test_the_player_sells_a_recipe_they_know_and_still_knows_it(make_package: MakePackage) -> None:
    app = make_app(make_package)
    player_of(app).mind = Mind(recipes=[Bionic.POWER_CELL, Bionic.DATAJACK])

    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        greeted = next_of(ws, "player_state")
        player, tick = player_of(app), world_of(app).loop.tick
        ws.send_json({"type": "player_move", "position": {"x": 4, "y": 2, "map": CLINIC.map}})
        until(client, lambda: movement_of(app).entities().get(PLAYER_ID) == CLINIC)
        client.portal.call(tick)
        at_the_clinic = next_of(ws, "player_state")
        ws.send_json({"type": "sell_recipe", "recipe": "datajack"})
        until(client, lambda: player.money > 0)
        client.portal.call(tick)
        sold = next_of(ws, "player_state")

    assert [recipe["bionic"] for recipe in greeted["recipes"]] == ["power_cell", "datajack"]
    assert greeted["recipes"][1]["parts"] == {"copper_wire": 3, "usb_c_connector": 1}
    assert at_the_clinic["buyer"]["recipes"] == {"datajack": 15}
    assert sold["player"]["money"] == 15
    assert sold["player"]["mind"] == {"recipes": ["power_cell", "datajack"], "sold": ["datajack"]}
    assert "recipes" not in sold["buyer"]


def test_the_player_is_patched_up_and_has_a_bite_cleaned(make_package: MakePackage) -> None:
    app = make_app(make_package)
    player = player_of(app)
    player.money, player.health = 50, 0.5
    player.effects = [Effect(kind=EffectKind.RAT_BITE, strength=0.4, fades=0.25, since=START)]

    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        next_of(ws, "player_state")
        tick = world_of(app).loop.tick
        ws.send_json({"type": "player_move", "position": {"x": 4, "y": 2, "map": CLINIC.map}})
        until(client, lambda: movement_of(app).entities().get(PLAYER_ID) == CLINIC)
        client.portal.call(tick)
        at_the_clinic = next_of(ws, "player_state")
        ws.send_json({"type": "treat", "effect": None})
        ws.send_json({"type": "treat", "effect": "rat_bite"})
        until(client, lambda: player.money == 30)
        client.portal.call(tick)
        treated = next_of(ws, "player_state")

    assert [t["effect"] for t in at_the_clinic["buyer"]["treatments"]] == [None, "rat_bite"]
    assert at_the_clinic["buyer"]["treatments"][0]["price"] == 15
    assert "health" not in treated["player"] and "effects" not in treated["player"]
    assert "treatments" not in treated["buyer"]
