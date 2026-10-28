import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.app import create_app
from simile.persistence import player_of
from simile.player.lamp import Lamp, LampConfig
from simile.player.sync import PlayerSync
from simile.protocol import PlayerStateMessage
from simile.schema import PLAYER_ID, Item, ItemKind, Player, lamp
from simile.sim import Clock, EventBus, World, world_of
from simile.world import Movement, Point, movement_of
from simile.world.map import load_maps

MAPS = load_maps()
NOW = datetime(2026, 1, 1, 12, tzinfo=UTC)
MINUTE = 60.0
LIGHT = LampConfig().light
TUNNEL = Point(65, 15, "metro")
METRO_PLUG = Point(72, 15, "metro")
CAFE_PLUG = Point(16, 2, "coffee_shop_floor_0")
WIRE = Item(id="copper_wire", kind=ItemKind.SALVAGE, name="Copper wire", weight=1.5)

MakePackage = Callable[[dict[str, str]], str]


def with_lamp(charge: float = 1.0, on: bool = False) -> Player:
    return Player(items=[WIRE, lamp().model_copy(update={"charge": charge, "on": on})])


class Underground:
    def __init__(self, player: Player, at: Point = TUNNEL, speed: float = 1.0) -> None:
        self.player = player
        self.playing = True
        self.movement = Movement(MAPS, EventBus())
        self.movement.track(PLAYER_ID, at)
        self.lamp = Lamp(
            player, self.movement, Clock(NOW, speed=speed), playing=lambda: self.playing
        )

    def go(self, to: Point) -> None:
        self.movement.track(PLAYER_ID, to)

    def run(self, seconds: float, step: float = 1.0) -> None:
        for _ in range(round(seconds / step)):
            self.lamp.tick(step)

    @property
    def held(self) -> Item:
        [found] = [item for item in self.player.items if item.kind is ItemKind.LAMP]
        return found


def test_the_battery_runs_down_while_the_lamp_is_on() -> None:
    down = Underground(with_lamp(on=True))

    down.run(LIGHT / 2, step=0.25)

    assert down.held.charge == pytest.approx(0.5)
    assert down.held.on is True


def test_a_full_battery_lasts_two_minutes() -> None:
    assert LIGHT == 120


def test_it_runs_down_in_real_seconds_whatever_the_sims_speed() -> None:
    down = Underground(with_lamp(on=True), speed=10)

    down.run(10 * LIGHT / 2, step=2.5)

    assert down.held.charge == pytest.approx(0.5)


def test_the_battery_keeps_its_charge_while_the_lamp_is_off() -> None:
    down = Underground(with_lamp(charge=0.6))

    down.run(10 * MINUTE)

    assert down.held.charge == 0.6


def test_nothing_changes_while_nobody_is_playing() -> None:
    down = Underground(with_lamp(on=True))
    down.playing = False

    down.run(10 * MINUTE)

    assert down.held.charge == 1.0


@pytest.mark.parametrize("on", [False, True])
@pytest.mark.parametrize("plug", [METRO_PLUG, CAFE_PLUG], ids=["metro", "cafe"])
def test_it_charges_at_a_plug_on_or_off_up_to_full(plug: Point, on: bool) -> None:
    down = Underground(with_lamp(charge=0.2, on=on), at=plug)

    down.run(1.5, step=0.1)
    half = down.held.charge
    down.run(3, step=0.1)

    assert half == pytest.approx(0.7)
    assert down.held.charge == 1.0
    assert down.held.on is on


def test_it_charges_in_three_real_seconds_whatever_the_sims_speed() -> None:
    down = Underground(with_lamp(charge=0.0), at=METRO_PLUG, speed=20)

    down.run(30, step=0.1)
    partway = down.held.charge
    down.run(30, step=0.1)

    assert partway == pytest.approx(0.5)
    assert down.held.charge == 1.0


@pytest.mark.parametrize("off", [Point(71, 15, "metro"), Point(73, 15, "metro"), TUNNEL])
def test_it_charges_only_on_the_plugs_stand_tile(off: Point) -> None:
    down = Underground(with_lamp(charge=0.2), at=off)

    down.run(MINUTE)

    assert down.lamp.plug() is None
    assert down.held.charge == 0.2


def test_a_step_onto_the_plug_counts_as_the_server_reads_the_tile() -> None:
    down = Underground(with_lamp(charge=0.2), at=Point(71.6, 15, "metro"))

    assert down.lamp.plug() is not None and down.lamp.plug().id == "metro_plug"


def test_it_goes_out_when_the_battery_runs_flat() -> None:
    down = Underground(with_lamp(charge=0.01, on=True))

    down.run(MINUTE)

    assert down.held.charge == 0
    assert down.held.on is False


def test_a_flat_lamp_does_nothing_until_it_is_charged() -> None:
    down = Underground(with_lamp(charge=0.0))

    switched = down.lamp.switch(True)
    down.run(10 * MINUTE)
    still = down.held
    down.go(METRO_PLUG)
    down.run(0.3, step=0.1)
    charged = down.lamp.switch(True)

    assert not switched and still.charge == 0 and still.on is False
    assert charged and down.held.on is True and down.held.charge == pytest.approx(0.1)


def test_switching_on_and_off_says_whether_it_changed() -> None:
    down = Underground(with_lamp(charge=0.5))

    results = [down.lamp.switch(on) for on in (True, True, False, False)]

    assert results == [True, False, True, False]
    assert down.held.on is False and down.held.charge == 0.5


def test_switching_replaces_the_players_items_and_keeps_the_rest() -> None:
    player = with_lamp()
    before = player.items
    down = Underground(player)

    down.lamp.switch(True)

    assert player.items is not before
    assert player.items == [WIRE, before[1].model_copy(update={"on": True})]
    assert before[1].on is False


def test_without_a_lamp_there_is_nothing_to_switch_or_drain() -> None:
    down = Underground(Player(items=[WIRE]), at=METRO_PLUG)

    assert not down.lamp.switch(True)
    down.run(MINUTE)
    assert down.player.items == [WIRE]


@pytest.mark.parametrize(
    ("start", "on", "at", "end"), [(0.6234, False, METRO_PLUG, 1.0), (0.0034, True, TUNNEL, 0.0)]
)
def test_a_charge_that_reaches_full_or_flat_is_sent_off_the_step(
    start: float, on: bool, at: Point, end: float
) -> None:
    down = Underground(with_lamp(charge=start, on=on), at=at)
    sent: list[PlayerStateMessage] = []
    sync = PlayerSync(down.player, lambda: None, sent.append)

    for _ in range(round(MINUTE / 0.1)):
        down.lamp.tick(0.1)
        sync.tick(0.1)

    [last] = [item for item in sent[-1].player.items if item.kind is ItemKind.LAMP]
    assert last.charge == end


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


def lamp_of(message: dict[str, Any]) -> dict[str, Any]:
    [found] = [item for item in message["player"]["items"] if item["kind"] == "lamp"]
    return found


def test_the_client_switches_the_lamp_and_hears_it_run_down_and_charge(
    make_package: MakePackage,
) -> None:
    app = make_app(make_package)

    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        tick = world_of(app).loop.tick
        next_of(ws, "player_state")
        ws.send_json({"type": "player_move", "position": {"x": 65, "y": 15, "map": "metro"}})
        deadline = time.monotonic() + 2
        while client.portal.call(movement_of(app).entities).get(PLAYER_ID) != TUNNEL:
            assert time.monotonic() < deadline, "the server never had the player there"
            time.sleep(0.001)
        ws.send_json({"type": "lamp", "on": True})
        switched = next_of(ws, "player_state")
        client.portal.call(lambda: setattr(player_of(app), "items", with_lamp(0.5, True).items))
        client.portal.call(tick)
        drained = next_of(ws, "player_state")
        ws.send_json({"type": "player_move", "position": {"x": 72, "y": 15, "map": "metro"}})
        deadline = time.monotonic() + 2
        while client.portal.call(movement_of(app).entities).get(PLAYER_ID) != METRO_PLUG:
            assert time.monotonic() < deadline, "the server never had the player at the plug"
            time.sleep(0.001)
        client.portal.call(lambda: [tick() for _ in range(400)])
        ws.send_json({"type": "lamp", "on": False})
        charged = [next_of(ws, "player_state")]
        while lamp_of(charged[-1])["on"]:
            charged.append(next_of(ws, "player_state"))

    assert lamp_of(switched)["on"] is True and lamp_of(switched)["charge"] == 1
    assert lamp_of(drained)["charge"] < 0.5
    rising = [lamp_of(message)["charge"] for message in charged[:-1]]
    assert rising == sorted(rising) and rising[0] > lamp_of(drained)["charge"]
    assert rising[-1] == 1, "the full charge is sent before the switch"


def test_a_collapse_switches_the_lamp_off(make_package: MakePackage) -> None:
    app = make_app(make_package)

    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        player = player_of(app)
        next_of(ws, "player_state")
        ws.send_json({"type": "player_move", "position": {"x": 65, "y": 15, "map": "metro"}})
        ws.send_json({"type": "lamp", "on": True})
        switched = next_of(ws, "player_state")
        client.portal.call(lambda: setattr(player, "hunger", 1 - 1e-9))
        client.portal.call(world_of(app).loop.tick)
        next_of(ws, "player_collapsed")
        woken = next_of(ws, "player_state")

    assert lamp_of(switched)["on"] is True
    assert lamp_of(woken)["on"] is False
