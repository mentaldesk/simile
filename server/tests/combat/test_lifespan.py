import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from starlette.testclient import TestClient

from simile.app import create_app
from simile.creatures.engine import creatures_of
from simile.creatures.kinds import DOG
from simile.persistence import player_of
from simile.schema import PLAYER_ID, Item, ItemKind, MapTile, Material
from simile.sim import Clock, World, world_of
from simile.world import Point, movement_of

MakePackage = Callable[[dict[str, str]], str]

START = datetime(2026, 1, 1, 10, tzinfo=UTC)
LIFESPANS = ("behaviour", "creatures", "economy", "memory", "protocol", "world")


def next_of(ws: Any, type: str) -> dict[str, Any]:
    for _ in range(500):
        if (message := ws.receive_json())["type"] == type:
            return message
    raise AssertionError(f"no {type}")


def test_a_held_back_move_then_fire_hits_from_there_and_reload_tops_it_up(
    make_package: MakePackage,
) -> None:
    files = {f"{m}/lifespan.py": f"from simile.{m}.lifespan import lifespan\n" for m in LIFESPANS}
    files["protocol/routes.py"] = "from simile.protocol.routes import routes\n"
    files["player/lifespan.py"] = "from simile.player.lifespan import running\n"
    files["combat/lifespan.py"] = "from simile.combat.lifespan import running\n"
    app = create_app(make_package(files))
    app.state.world = World(Clock(START))

    with TestClient(app) as client:
        dog = client.portal.call(
            lambda: creatures_of(app).spawn(DOG, MapTile(map="metro", x=66, y=15))
        )
        player_of(app).items = [
            Item(
                id="pistol",
                kind=ItemKind.WEAPON,
                name="Plastic pistol",
                weight=0.5,
                material=Material.PLASTIC,
                rounds=2,
                capacity=6,
                condition=1.0,
            ),
            Item(
                id="rounds",
                kind=ItemKind.ROUNDS,
                name="Plastic rounds",
                weight=0.02,
                amount=3.0,
                material=Material.PLASTIC,
            ),
        ]
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "player_move", "position": {"x": 40, "y": 15, "map": "metro"}})
            ws.send_json({"type": "player_move", "position": {"x": 62, "y": 15, "map": "metro"}})
            ws.send_json({"type": "fire", "facing": "east"})
            hit = next_of(ws, "creature_hit")
            moved = next_of(ws, "creature_moved")

            deadline = time.monotonic() + 2
            while client.portal.call(movement_of(app).entities).get(PLAYER_ID) != Point(
                62, 15, "metro"
            ):
                assert time.monotonic() < deadline
                time.sleep(0.001)
            client.portal.call(world_of(app).loop.tick)
            fired = next_of(ws, "player_state")

            ws.send_json({"type": "reload"})
            deadline = time.monotonic() + 2
            while player_of(app).items[0].rounds != 4:
                assert time.monotonic() < deadline
                time.sleep(0.001)
            client.portal.call(world_of(app).loop.tick)
            reloaded = next_of(ws, "player_state")

    assert hit == {"type": "creature_hit", "creature_id": dog.id}
    assert moved["creature"]["id"] == dog.id
    assert 0 < moved["creature"]["health"] < 1
    weapon, stack = fired["player"]["items"]
    assert weapon["rounds"] == 1
    assert weapon["condition"] < 1
    assert stack["amount"] == 3
    assert [item["id"] for item in reloaded["player"]["items"]] == ["pistol"]
    assert reloaded["player"]["items"][0]["rounds"] == 4
