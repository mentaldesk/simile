import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.app import create_app
from simile.clinic.doctor import DOCTOR
from simile.economy import OUTSIDE, PLAYER, Kind
from simile.economy.economy import economy_of
from simile.persistence import player_of
from simile.schema import PLAYER_ID, Player
from simile.sim import Clock, World, world_of
from simile.world import Point, movement_of

MakePackage = Callable[[dict[str, str]], str]

START = datetime(2026, 1, 1, 10, tzinfo=UTC)
LIFESPANS = ("behaviour", "economy", "memory", "protocol", "world")
CLINIC = Point(4, 2, "clinic_floor_0")


def make_app(make_package: MakePackage) -> Starlette:
    files = {f"{m}/lifespan.py": f"from simile.{m}.lifespan import lifespan\n" for m in LIFESPANS}
    files["protocol/routes.py"] = "from simile.protocol.routes import routes\n"
    files["player/lifespan.py"] = "from simile.player.lifespan import running\n"
    files["clinic/lifespan.py"] = "from simile.clinic.lifespan import running\n"
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


def test_the_player_sells_a_kidney_and_is_fitted_with_the_legs(make_package: MakePackage) -> None:
    app = make_app(make_package)

    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        next_of(ws, "player_state")
        player, tick = player_of(app), world_of(app).loop.tick
        ws.send_json({"type": "player_move", "position": {"x": 4, "y": 2, "map": CLINIC.map}})
        until(client, lambda: movement_of(app).entities().get(PLAYER_ID) == CLINIC)
        client.portal.call(tick)
        at_the_clinic = next_of(ws, "player_state")
        ws.send_json({"type": "fit", "bionic": "hydraulic_legs", "part": "legs"})
        ws.send_json({"type": "sell_part", "part": "left_kidney"})
        until(client, lambda: player.money == 100)
        client.portal.call(tick)
        sold = next_of(ws, "player_state")
        ws.send_json({"type": "fit", "bionic": "hydraulic_legs", "part": "legs"})
        until(client, lambda: player.money == 20)
        client.portal.call(tick)
        fitted = next_of(ws, "player_state")
        economy = economy_of(app)

    assert at_the_clinic["buyer"]["parts"] == {"left_kidney": 100.0}
    assert [f["bionic"] for f in at_the_clinic["buyer"]["fittings"]] == [
        "hydraulic_legs",
        "sprint_legs",
        "datajack",
        "infrared_eye",
    ]
    assert sold["player"]["body"]["left_kidney"] == "sold"
    assert "parts" not in sold["buyer"]
    assert fitted["player"]["body"]["legs"] == "hydraulic_legs"
    assert fitted["player"]["money"] == 20
    assert [f["bionic"] for f in fitted["buyer"]["fittings"]] == [
        "spring_legs",
        "datajack",
        "infrared_eye",
    ]
    entries = [(e.kind, e.payer, e.payee, e.amount) for e in economy.ledger.entries]
    assert entries == [
        (Kind.SALVAGE, OUTSIDE, PLAYER, 100),
        (Kind.PURCHASE, PLAYER, OUTSIDE, 80),
    ]
    assert economy.ledger.net(PLAYER) == 20
    assert economy.ledger.gap(economy.money) == pytest.approx(0)
    assert Player.model_validate(fitted["player"]).humanity < 1
