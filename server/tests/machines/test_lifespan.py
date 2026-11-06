import sys
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

import simile.machines
from simile.app import create_app
from simile.machines.workshop import Offer
from simile.persistence import player_of
from simile.schema import PLAYER_ID, Item, ItemKind, Material, Player, Product
from simile.sim import Clock, World, world_of
from simile.world import Point, movement_of

MakePackage = Callable[[dict[str, str]], str]
LIFESPANS = ("behaviour", "economy", "memory", "protocol", "world")
PRINTER = Point(9, 2, "maker_space_floor_0")
ROUNDS = Item(
    id="fixture_magazine",
    kind=ItemKind.ROUNDS,
    name="Rounds",
    weight=0.01,
    amount=6.0,
    material=Material.PLASTIC,
)


def make_app(make_package: MakePackage) -> Starlette:
    files = {f"{m}/lifespan.py": f"from simile.{m}.lifespan import lifespan\n" for m in LIFESPANS}
    files["protocol/routes.py"] = "from simile.protocol.routes import routes\n"
    files["machines/lifespan.py"] = "from simile.machines.lifespan import running\n"
    app = create_app(make_package(files))
    app.state.world = World(Clock(datetime(2026, 1, 1, 10, tzinfo=UTC)))
    return app


def next_of(ws: Any, type: str, seconds: float = 5) -> dict[str, Any]:
    """Fails rather than hangs on a message that never comes: `receive_json` has no timeout."""

    def read() -> dict[str, Any]:
        for _ in range(500):
            if (message := ws.receive_json())["type"] == type:
                return message
        raise AssertionError(f"no {type}")

    pool = ThreadPoolExecutor(1)
    try:
        return pool.submit(read).result(timeout=seconds)
    finally:
        pool.shutdown(wait=False)


def until(client: TestClient, done: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 2
    while not client.portal.call(done):
        assert time.monotonic() < deadline, "the server never got there"
        time.sleep(0.001)


def test_make_reaches_what_a_machine_offers(make_package: MakePackage) -> None:
    app = make_app(make_package)
    made: list[Player] = []

    def make(player: Player) -> bool:
        made.append(player)
        return True

    product = Product(item=ROUNDS, uses=Material.PLASTIC, cost=2)

    with TestClient(app) as client:
        player_of(app).repaired = ["printer_3d"]
        app.state.workshop.offer("printer_3d", Offer(product, make))
        with client.websocket_connect("/ws") as ws:
            next_of(ws, "snapshot")
            ws.send_json({"type": "player_move", "position": {"x": 9, "y": 2, "map": PRINTER.map}})
            until(client, lambda: movement_of(app).entities().get(PLAYER_ID) == PRINTER)
            ws.send_json({"type": "make", "machine": "printer_3d", "item": ROUNDS.id})
            until(client, lambda: bool(made))
        player = player_of(app)

    assert made == [player]


def test_a_module_beside_the_workshop_adds_its_offers_at_startup(
    make_package: MakePackage, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "q4_fixture_offers.py").write_text(
        "from simile.machines.workshop import Offer\n"
        "from simile.schema import Item, ItemKind, Material, Product\n"
        "ROUNDS = Item(id='fixture_rounds', kind=ItemKind.ROUNDS, name='Rounds', weight=0.01, "
        "amount=6.0, material=Material.PLASTIC)\n"
        "def offers(workshop):\n"
        "    product = Product(item=ROUNDS, uses=Material.PLASTIC, cost=2)\n"
        "    workshop.offer('printer_3d', Offer(product, lambda player: True))\n"
    )
    monkeypatch.setattr(simile.machines, "__path__", [*simile.machines.__path__, str(tmp_path)])
    monkeypatch.delitem(sys.modules, "simile.machines.q4_fixture_offers", raising=False)
    app = make_app(make_package)
    player_of(app).repaired = ["printer_3d"]

    try:
        with TestClient(app) as client, client.websocket_connect("/ws") as ws:
            snapshot = next_of(ws, "snapshot")
    finally:
        sys.modules.pop("simile.machines.q4_fixture_offers", None)

    [printer, _] = snapshot["machines"]
    assert "fixture_rounds" in [product["item"]["id"] for product in printer["makes"]]


def test_a_change_to_an_offer_reaches_the_client_on_the_sim_loop(
    make_package: MakePackage,
) -> None:
    app = make_app(make_package)
    product = Product(item=ROUNDS, uses=Material.PLASTIC, cost=2)
    player_of(app).repaired = ["printer_3d"]

    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        next_of(ws, "snapshot")
        offered = Offer(lambda player: product if player.money else None, lambda player: True)
        app.state.workshop.offer("printer_3d", offered)
        player_of(app).money = 1.0
        client.portal.call(world_of(app).loop.tick)
        changed = next_of(ws, "machine_changed")

    assert ROUNDS.id in [made["item"]["id"] for made in changed["machine"]["makes"]]


def test_the_snapshot_holds_both_machines_broken(make_package: MakePackage) -> None:
    with TestClient(make_app(make_package)) as client, client.websocket_connect("/ws") as ws:
        snapshot = next_of(ws, "snapshot")

    assert [(m["id"], m["state"]) for m in snapshot["machines"]] == [
        ("printer_3d", "broken"),
        ("recycler", "broken"),
    ]


def test_a_repair_is_sent_and_in_the_next_snapshot(make_package: MakePackage) -> None:
    app = make_app(make_package)
    parts = [
        Item(id=id, kind=ItemKind.PART, name=id, weight=0.1)
        for id in ("metal_sheet", "linear_actuator", "copper_wire", "copper_wire")
    ]

    with TestClient(app) as client:
        player_of(app).items = parts
        with client.websocket_connect("/ws") as ws:
            next_of(ws, "snapshot")
            ws.send_json({"type": "player_move", "position": {"x": 9, "y": 2, "map": PRINTER.map}})
            until(client, lambda: movement_of(app).entities().get(PLAYER_ID) == PRINTER)
            ws.send_json({"type": "repair", "machine": "printer_3d"})
            changed = next_of(ws, "machine_changed")
            items = player_of(app).items
        with client.websocket_connect("/ws") as ws:
            snapshot = next_of(ws, "snapshot")

    assert items == []
    assert changed["machine"]["state"] == "working"
    assert changed["machine"]["parts"] == {}
    assert [product["item"]["id"] for product in changed["machine"]["makes"]] == [
        "plastic_pistol",
        "plastic_rounds",
    ]
    assert [(m["id"], m["state"]) for m in snapshot["machines"]] == [
        ("printer_3d", "working"),
        ("recycler", "broken"),
    ]
