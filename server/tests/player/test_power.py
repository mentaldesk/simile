import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.app import create_app
from simile.persistence import player_of
from simile.player.lamp import Lamp
from simile.player.power import DEFAULT_POWER, Power, runs
from simile.player.sync import PlayerSync
from simile.schema import PLAYER_ID, Bionic, Body, Player
from simile.sim import Clock, EventBus, World, world_of
from simile.world import Movement, Point, movement_of
from simile.world.map import load_maps

MAPS = load_maps()
NOW = datetime(2026, 1, 1, 12, tzinfo=UTC)
HOUR = 3600.0
TUNNEL = Point(65, 15, "metro")
PLUG = Point(72, 15, "metro")
CELL, CELL_2 = Bionic.POWER_CELL, Bionic.POWER_CELL_2
JACK, LEGS, FEET, EYE = (
    Bionic.DATAJACK,
    Bionic.BIONIC_LEGS,
    Bionic.SPRING_FEET,
    Bionic.INFRARED_EYE,
)
THREE = Body(stomach=CELL, vertebra=JACK, legs=LEGS, feet=FEET)

MakePackage = Callable[[dict[str, str]], str]


class Cell:
    def __init__(self, player: Player, at: Point = TUNNEL, speed: float = 1.0) -> None:
        self.player = player
        self.playing = True
        self.collapses = 0
        self.movement = Movement(MAPS, EventBus())
        self.movement.track(PLAYER_ID, at)
        clock = Clock(NOW, speed=speed)
        self.lamp = Lamp(player, self.movement, clock)
        self.power = Power(
            player,
            clock,
            charging=self.lamp.charging,
            playing=lambda: self.playing,
            collapse=self.collapse,
        )

    def collapse(self) -> None:
        self.collapses += 1

    def run(self, seconds: float, step: float = 1.0) -> None:
        for _ in range(round(seconds / step)):
            self.power.tick(step)


def test_power_drains_faster_with_each_bionic_fitted() -> None:
    alone = Cell(Player(body=Body(stomach=CELL)))
    jacked = Cell(Player(body=Body(stomach=CELL, vertebra=JACK)))
    three = Cell(Player(body=THREE))

    for cell in (alone, jacked, three):
        cell.run(HOUR, step=60)

    assert alone.player.power == pytest.approx(0.8)
    assert jacked.player.power == pytest.approx(0.7)
    assert three.player.power == pytest.approx(0.5)


def test_without_a_cell_power_stays_full() -> None:
    cell = Cell(Player(body=Body(vertebra=JACK)))

    cell.run(HOUR * 10, step=60)

    assert cell.player.power == 1
    assert cell.collapses == 0


def test_power_waits_while_nobody_is_playing() -> None:
    cell = Cell(Player(body=THREE, power=0.5))
    cell.playing = False

    cell.run(HOUR, step=60)

    assert cell.player.power == 0.5


@pytest.mark.parametrize("speed", [1.0, 10.0])
def test_a_plug_charges_it_from_flat_to_full_in_three_real_seconds(speed: float) -> None:
    cell = Cell(Player(body=THREE, power=0.01), at=PLUG, speed=speed)

    cell.run(1.4 * speed, step=0.1)
    partway = cell.player.power
    cell.run(1.6 * speed, step=0.1)

    assert partway == pytest.approx(0.01 + 1.4 / 3)
    assert cell.player.power == 1
    assert cell.collapses == 0


def test_running_flat_collapses_them_and_they_wake_with_some_charge() -> None:
    cell = Cell(Player(body=THREE, power=0.001))

    cell.power.tick(60)

    assert cell.collapses == 1
    assert cell.player.power == DEFAULT_POWER.waking


def test_the_first_cell_runs_three_other_bionics_and_a_bigger_cell_more() -> None:
    assert runs(Body(stomach=CELL, vertebra=JACK, legs=LEGS), FEET)
    assert not runs(THREE, EYE)
    assert runs(THREE.model_copy(update={"stomach": CELL_2}), EYE)


def test_an_upgrade_in_place_of_a_bionic_takes_no_more_of_the_cell() -> None:
    assert runs(THREE, Bionic.BIONIC_LEGS_2)
    assert runs(THREE, Bionic.SPRING_FEET_2)


def test_a_cell_runs_what_is_already_fitted() -> None:
    four = THREE.model_copy(update={"right_eye": EYE})

    assert runs(four, CELL_2)
    assert not runs(four, CELL)
    assert runs(Body(), CELL)


def test_a_change_to_power_alone_waits_until_it_has_moved_a_hundredth() -> None:
    player, sent = Player(body=THREE, power=0.5), []
    sync = PlayerSync(player, lambda: None, sent.append)

    player.power = 0.505
    sync.update()
    assert sent == []
    player.power = 0.51
    sync.update()
    assert [message.player.power for message in sent] == [0.51]


def make_app(make_package: MakePackage) -> Starlette:
    lifespans = ("behaviour", "economy", "memory", "protocol", "world")
    files = {f"{m}/lifespan.py": f"from simile.{m}.lifespan import lifespan\n" for m in lifespans}
    files["protocol/routes.py"] = "from simile.protocol.routes import routes\n"
    files["player/lifespan.py"] = "from simile.player.lifespan import running\n"
    app = create_app(make_package(files))
    app.state.world = World(Clock(NOW))
    return app


def next_of(ws: Any, type: str) -> dict[str, Any]:
    for _ in range(500):
        if (message := ws.receive_json())["type"] == type:
            return message
    raise AssertionError(f"no {type}")


def test_a_flat_cell_collapses_them_for_power_and_a_plug_at_home_charges_it(
    make_package: MakePackage,
) -> None:
    app = make_app(make_package)

    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        tick, player = world_of(app).loop.tick, player_of(app)
        next_of(ws, "player_state")
        ws.send_json({"type": "player_move", "position": {"x": 65, "y": 15, "map": "metro"}})
        deadline = time.monotonic() + 2
        while client.portal.call(movement_of(app).entities).get(PLAYER_ID) != TUNNEL:
            assert time.monotonic() < deadline, "the server never had the player there"
            time.sleep(0.001)
        client.portal.call(lambda: setattr(player, "body", THREE))
        client.portal.call(lambda: setattr(player, "power", 1e-9))
        client.portal.call(tick)
        collapsed = next_of(ws, "player_collapsed")
        woken = next_of(ws, "player_state")
        client.portal.call(lambda: [tick() for _ in range(40)])
        charging = [next_of(ws, "player_state")]
        while "power" in charging[-1]["player"]:
            charging.append(next_of(ws, "player_state"))

    assert collapsed["cause"] == "power"
    assert woken["player"]["power"] == DEFAULT_POWER.waking
    assert woken["player"]["hunger"] == 0
    assert woken.get("meal") is None
    rising = [message["player"].get("power", 1) for message in charging]
    assert rising == sorted(rising) and rising[0] > DEFAULT_POWER.waking and rising[-1] == 1
