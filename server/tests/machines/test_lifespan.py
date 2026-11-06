import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.app import create_app
from simile.persistence import player_of
from simile.schema import PLAYER_ID, Item, ItemKind
from simile.sim import Clock, World
from simile.world import Point, movement_of

MakePackage = Callable[[dict[str, str]], str]
LIFESPANS = ("behaviour", "economy", "memory", "protocol", "world")
PRINTER = Point(9, 2, "maker_space_floor_0")


def make_app(make_package: MakePackage) -> Starlette:
    files = {f"{m}/lifespan.py": f"from simile.{m}.lifespan import lifespan\n" for m in LIFESPANS}
    files["protocol/routes.py"] = "from simile.protocol.routes import routes\n"
    files["machines/lifespan.py"] = "from simile.machines.lifespan import running\n"
    app = create_app(make_package(files))
    app.state.world = World(Clock(datetime(2026, 1, 1, 10, tzinfo=UTC)))
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
            assert client.portal.call(app.state.workshop.repair, "printer_3d")
            changed = next_of(ws, "machine_changed")
        with client.websocket_connect("/ws") as ws:
            snapshot = next_of(ws, "snapshot")

    assert changed["machine"] == {
        "id": "printer_3d",
        "kind": "printer",
        "state": "working",
        "parts": {},
        "makes": [],
    }
    assert [(m["id"], m["state"]) for m in snapshot["machines"]] == [
        ("printer_3d", "working"),
        ("recycler", "broken"),
    ]
