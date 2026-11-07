import contextlib
import queue
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from simile.app import create_app
from simile.behaviour import Behaviour
from simile.memory import MemoryStore
from simile.npc import load_npcs
from simile.persistence import WorldStore, capture
from simile.player.corpses import Death, Salvage
from simile.player.stash import Lockers, fitting
from simile.protocol import TakeMessage, Vital
from simile.schema import (
    PLAYER_ID,
    Corpse,
    Item,
    ItemKind,
    MapTile,
    Material,
    Player,
    Stash,
    lamp,
)
from simile.sim import Clock, FakeWallClock, World
from simile.world import Movement, Point, movement_of
from simile.world.map import load_maps
from simile.world.paths import Spot

MAPS = load_maps()
NOW = datetime(2026, 1, 1, 12, tzinfo=UTC)
AT_THE_LOCKERS = Point(7, 2, "maker_space_floor_2")
WIRE = Item(id="copper_wire", kind=ItemKind.SALVAGE, name="Copper wire", weight=1.5)
ANVIL = Item(id="anvil", kind=ItemKind.PART, name="Anvil", weight=30)
FEATHER = Item(id="feather", kind=ItemKind.SALVAGE, name="Feather", weight=0)
LIFESPANS = ("behaviour", "economy", "memory", "protocol", "world")


def plastic(amount: float, weight: float = 0.5) -> Item:
    return Item(
        id="plastic",
        kind=ItemKind.MATERIAL,
        name="Plastic",
        weight=weight,
        amount=amount,
        material=Material.PLASTIC,
    )


def rounds(amount: int, weight: float = 0.1) -> Item:
    return Item(
        id="plastic_rounds",
        kind=ItemKind.ROUNDS,
        name="Plastic rounds",
        weight=weight,
        amount=amount,
        material=Material.PLASTIC,
    )


def pistol(loaded: int = 4, condition: float = 0.7) -> Item:
    return Item(
        id="plastic_pistol",
        kind=ItemKind.WEAPON,
        name="Plastic pistol",
        weight=0.5,
        material=Material.PLASTIC,
        rounds=loaded,
        capacity=6,
        condition=condition,
    )


def lockers_for(player: Player, at: Point | None = AT_THE_LOCKERS) -> Lockers:
    movement = Movement(MAPS, World(Clock(NOW), FakeWallClock()).bus)
    if at is not None:
        movement.track(PLAYER_ID, at)
    return Lockers(player, movement)


def test_the_tests_stand_on_the_lockers_stand_tile() -> None:
    lockers = next(i for i in MAPS[AT_THE_LOCKERS.map].interactables if i.id == "lockers")
    assert [(tile.x, tile.y) for tile in lockers.stand] == [(AT_THE_LOCKERS.x, AT_THE_LOCKERS.y)]


def test_storing_and_taking_move_an_item_both_ways() -> None:
    player = Player(items=[lamp(), WIRE])
    lockers = lockers_for(player)

    assert lockers.move("copper_wire", "store")
    assert player.items == [lamp()]
    assert player.stash.items == [WIRE]

    assert lockers.move("copper_wire", "take")
    assert player.items == [lamp(), WIRE]
    assert player.stash == Stash()


@pytest.mark.parametrize(
    "at",
    [
        None,
        Point(6, 2, "maker_space_floor_2"),
        Point(7, 1, "maker_space_floor_2"),
        Point(7, 2, "metro"),
    ],
)
def test_nothing_moves_away_from_the_lockers(at: Point | None) -> None:
    player = Player(items=[WIRE], stash=Stash(items=[plastic(2)]))
    lockers = lockers_for(player, at)

    assert not lockers.move("copper_wire", "store")
    assert not lockers.move("plastic", "take")
    assert player.items == [WIRE]
    assert player.stash.items == [plastic(2)]


def test_nothing_moves_of_what_is_not_there() -> None:
    player = Player(items=[WIRE])
    lockers = lockers_for(player)

    assert not lockers.move("anvil", "store")
    assert not lockers.move("copper_wire", "take")
    assert player.items == [WIRE]


def test_an_item_too_heavy_for_the_stash_stays_where_it_was() -> None:
    player = Player(items=[ANVIL], carry_limit=40)

    assert not lockers_for(player).move("anvil", "store")
    assert player.items == [ANVIL]
    assert player.stash == Stash()


def test_an_item_too_heavy_to_carry_stays_in_the_stash() -> None:
    player = Player(items=[], stash=Stash(items=[ANVIL], limit=40))

    assert not lockers_for(player).move("anvil", "take")
    assert player.stash.items == [ANVIL]
    assert player.items == []


def test_the_limit_holds_as_the_stash_fills() -> None:
    ballast = Item(id="ballast", kind=ItemKind.PART, name="Ballast", weight=19)
    bolt = Item(id="bolt", kind=ItemKind.PART, name="Bolt", weight=1)
    player = Player(items=[WIRE, bolt], stash=Stash(items=[ballast]))
    lockers = lockers_for(player)

    assert not lockers.move("copper_wire", "store")
    assert lockers.move("bolt", "store")
    assert player.stash.load == 20
    assert not lockers.move("copper_wire", "store")
    assert player.items == [WIRE]


def test_as_much_of_a_material_as_fits_is_stored_and_the_rest_stays_in_place() -> None:
    player = Player(items=[lamp(), plastic(10), WIRE], stash=Stash(limit=2))

    assert lockers_for(player).move("plastic", "store")

    assert player.stash.items == [plastic(4)]
    assert player.stash.load == 2
    assert player.items == [lamp(), plastic(6), WIRE]


def test_as_much_of_a_material_as_fits_is_taken_and_the_rest_stays_stashed() -> None:
    player = Player(items=[], carry_limit=1.25, stash=Stash(items=[plastic(10)]))

    assert lockers_for(player).move("plastic", "take")

    assert player.items == [plastic(2.5)]
    assert player.stash.items == [plastic(7.5)]


def test_taking_counts_what_they_already_carry_and_joins_it() -> None:
    player = Player(items=[plastic(2), WIRE], carry_limit=4, stash=Stash(items=[plastic(10)]))

    assert lockers_for(player).move("plastic", "take")

    assert player.items == [plastic(5), WIRE]
    assert player.load == player.carry_limit
    assert player.stash.items == [plastic(7)]


def test_rounds_taken_stop_at_the_carry_limit_and_join_what_they_carry() -> None:
    player = Player(items=[WIRE, rounds(2)], carry_limit=2, stash=Stash(items=[rounds(10)]))

    assert lockers_for(player).move("plastic_rounds", "take")

    assert player.items == [WIRE, rounds(5)]
    assert player.stash.items == [rounds(7)]


def test_an_item_taken_fits_exactly_or_stays_with_what_they_carry_counted() -> None:
    bolts = Item(id="bolts", kind=ItemKind.PART, name="Bolts", weight=13.5)
    player = Player(items=[bolts], stash=Stash(items=[WIRE, WIRE, plastic(1)]))
    lockers = lockers_for(player)

    assert lockers.move("copper_wire", "take")
    assert player.items == [bolts, WIRE]
    assert not lockers.move("copper_wire", "take")
    assert not lockers.move("plastic", "take")
    assert player.stash.items == [WIRE, plastic(1)]


def test_a_stack_joins_any_of_its_id_already_there() -> None:
    player = Player(items=[plastic(1), rounds(6)], stash=Stash(items=[plastic(2), rounds(3)]))
    lockers = lockers_for(player)

    assert lockers.move("plastic", "store")
    assert lockers.move("plastic_rounds", "store")
    assert player.stash.items == [plastic(3), rounds(9)]
    assert player.items == []

    assert lockers.move("plastic", "take")
    assert player.items == [plastic(3)]


def test_rounds_move_whole() -> None:
    player = Player(items=[rounds(10)], stash=Stash(limit=0.35))

    assert lockers_for(player).move("plastic_rounds", "store")

    assert player.stash.items == [rounds(3)]
    assert player.items == [rounds(7)]


def test_what_weighs_nothing_moves_into_a_full_stash() -> None:
    player = Player(items=[FEATHER, rounds(2, weight=0)], stash=Stash(items=[ANVIL], limit=30))
    lockers = lockers_for(player)

    assert lockers.move("feather", "store")
    assert lockers.move("plastic_rounds", "store")
    assert player.items == []
    assert player.stash.items == [ANVIL, FEATHER, rounds(2, weight=0)]


@pytest.mark.parametrize(
    ("item", "room", "fits"),
    [
        (rounds(6), 0.3, 3),
        (rounds(6, weight=0.01), 0.03, 3),
        (rounds(6), 0.05, 0),
        (rounds(6), -1, 0),
        (plastic(6, weight=0.1), 0.3, 3),
        (plastic(0.1 + 0.2, weight=1), 0.3, 0.1 + 0.2),
        (plastic(3.000000002, weight=1), 3, 3.000000002),
        (plastic(2, weight=1), 1.2345678, 1.234567),
        (plastic(2, weight=1), 0.000002, 0.000002),
        (plastic(2, weight=1), 1e-12, 0),
        (plastic(2, weight=1), -1, 0),
        (plastic(2, weight=0), -1, 2),
        (WIRE, 1.5 - 1e-12, 1),
        (WIRE, 1.4, 0),
    ],
)
def test_what_fits_is_not_fooled_by_floats(item: Item, room: float, fits: float) -> None:
    assert fitting(item, room) == fits


def test_a_float_sum_leaves_no_dust_behind() -> None:
    stack = plastic(0.1 + 0.2, weight=1)
    player = Player(items=[stack], stash=Stash(limit=0.3))

    assert lockers_for(player).move("plastic", "store")
    assert player.items == []
    assert player.stash.items == [stack]


def test_a_tiny_gap_in_a_full_stash_moves_nothing() -> None:
    player = Player(items=[plastic(2)], stash=Stash(items=[plastic(39.9999999999)]))

    assert not lockers_for(player).move("plastic", "store")
    assert player.items == [plastic(2)]


def test_a_split_stack_reloads() -> None:
    player = Player(items=[plastic(3), rounds(5)], stash=Stash(limit=0.7))
    lockers = lockers_for(player)

    assert lockers.move("plastic", "store")
    assert not lockers.move("plastic_rounds", "store")
    reloaded = Player.model_validate_json(player.model_dump_json())

    assert reloaded == player
    assert reloaded.stash.items == [plastic(1.4)]
    assert reloaded.items[0] == plastic(1.6)


def test_a_weapon_keeps_its_rounds_and_condition_and_only_the_first_moves() -> None:
    worn, new = pistol(loaded=2, condition=0.4), pistol(loaded=6, condition=1)
    player = Player(items=[worn, new])
    lockers = lockers_for(player)

    assert lockers.move("plastic_pistol", "store")
    assert player.stash.items == [worn]
    assert player.items == [new]

    assert lockers.move("plastic_pistol", "store")
    assert player.stash.items == [worn, new]

    assert lockers.move("plastic_pistol", "take")
    assert player.items == [worn]
    assert player.items[0].rounds == 2
    assert player.items[0].condition == 0.4


def test_a_lit_lamp_goes_off_in_the_lockers_and_keeps_its_charge() -> None:
    lit = lamp().model_copy(update={"on": True, "charge": 0.4})
    player = Player(items=[lit])
    lockers = lockers_for(player)

    assert lockers.move("lamp", "store")
    assert player.stash.items[0].on is False
    assert lockers.move("lamp", "take")
    assert player.items[0].on is False
    assert player.items[0].charge == 0.4


def test_the_stash_survives_the_world_being_saved_and_loaded(tmp_path: Path) -> None:
    worn = pistol(loaded=2, condition=0.4)
    player = Player(items=[lamp(), worn, plastic(3)])
    lockers = lockers_for(player)
    assert lockers.move("plastic_pistol", "store")
    assert lockers.move("plastic", "store")
    world = World(Clock(NOW), FakeWallClock())
    behaviour = Behaviour(
        world.clock,
        world.bus,
        Movement(MAPS, world.bus),
        load_npcs()[:2],
        MemoryStore(":memory:"),
        seed=0,
    )
    path = tmp_path / "simile.db"

    with MemoryStore(path) as memory, WorldStore(memory) as store:
        store.save(capture(behaviour, player=player))
    with MemoryStore(path) as memory, WorldStore(memory) as store:
        loaded = store.load()

    assert loaded is not None
    assert loaded.player.stash.items == [worn, plastic(3)]
    assert loaded.player.stash.items[0].rounds == 2
    assert loaded.player.stash.items[0].condition == 0.4


def test_the_stash_survives_a_death_and_can_be_taken_from_after() -> None:
    worn = pistol(loaded=2, condition=0.4)
    player = Player(money=5, items=[lamp(), worn, plastic(3), WIRE])
    world = World(Clock(NOW), FakeWallClock())
    movement = Movement(MAPS, world.bus)
    movement.track(PLAYER_ID, AT_THE_LOCKERS)
    lockers = Lockers(player, movement)
    assert lockers.move("plastic_pistol", "store")
    assert lockers.move("plastic", "store")
    stored = player.stash.model_copy(deep=True)
    bed = Spot("maker_space_floor_2", 5, 2)

    movement.track(PLAYER_ID, Point(12, 15, "kapok_walk"))
    Death(player, movement, world.clock, bed=lambda: bed).die(Vital.HEALTH)

    assert player.stash == stored
    assert [item.id for item in player.corpses[0].items] == ["copper_wire"]
    assert [item.id for item in player.items] == ["lamp"]
    assert Player.model_validate_json(player.model_dump_json()).stash == stored

    movement.track(PLAYER_ID, AT_THE_LOCKERS)
    assert lockers.move("plastic_pistol", "take")
    assert player.items[-1] == worn


def corpse_beside_the_lockers(*items: Item) -> Corpse:
    at = MapTile(map=AT_THE_LOCKERS.map, x=8, y=2)
    return Corpse(id="corpse_1", owner=PLAYER_ID, at=at, money=0, items=list(items), bionics=[])


def salvage_of(player: Player) -> Salvage:
    movement = Movement(MAPS, World(Clock(NOW), FakeWallClock()).bus)
    movement.track(PLAYER_ID, AT_THE_LOCKERS)
    return Salvage(player, movement, None, None, {})  # type: ignore[arg-type]


def taking(item: str) -> TakeMessage:
    return TakeMessage(corpse="corpse_1", pile=None, item=item, bionic=None)


def test_a_corpse_beside_the_lockers_gives_what_fits_and_leaves_the_stash_alone() -> None:
    stored = Stash(items=[plastic(2)])
    player = Player(items=[lamp()], stash=stored, corpses=[corpse_beside_the_lockers(WIRE)])

    assert salvage_of(player).take(taking(WIRE.id))

    assert player.items == [lamp(), WIRE]
    assert player.corpses == []
    assert player.stash == stored


def test_storing_makes_room_for_a_corpse_beside_the_lockers_that_did_not_fit() -> None:
    crate = Item(id="crate", kind=ItemKind.PART, name="Crate", weight=8)
    bolts = Item(id="bolts", kind=ItemKind.PART, name="Bolts", weight=10)
    player = Player(items=[crate], corpses=[corpse_beside_the_lockers(bolts)])
    salvage = salvage_of(player)

    assert not salvage.take(taking("bolts"))
    assert lockers_for(player).move("crate", "store")
    assert salvage.take(taking("bolts"))

    assert player.items == [bolts]
    assert player.stash.items == [crate]
    assert player.corpses == []


def states_from(ws: Any) -> "queue.SimpleQueue[dict[str, Any]]":
    """Each `player_state` as it comes, read on a thread since `receive_json` has no timeout."""
    states: queue.SimpleQueue[dict[str, Any]] = queue.SimpleQueue()

    def read() -> None:
        with contextlib.suppress(Exception):
            while True:
                if (message := ws.receive_json())["type"] == "player_state":
                    states.put(message)

    threading.Thread(target=read, daemon=True).start()
    return states


def state_where(
    states: "queue.SimpleQueue[dict[str, Any]]", wanted: Callable[[dict[str, Any]], bool]
) -> dict[str, Any]:
    deadline = time.monotonic() + 5
    while True:
        try:
            state = states.get(timeout=max(deadline - time.monotonic(), 0))
        except queue.Empty:
            pytest.fail("no player_state followed the stash message")
        if wanted(state):
            return state


def stashed(state: dict[str, Any]) -> list[str]:
    return [item["id"] for item in state["player"].get("stash", {}).get("items", [])]


def test_the_stash_message_moves_things_and_the_player_state_follows(make_package: Any) -> None:
    files = {f"{m}/lifespan.py": f"from simile.{m}.lifespan import lifespan\n" for m in LIFESPANS}
    files["protocol/routes.py"] = "from simile.protocol.routes import routes\n"
    files["player/lifespan.py"] = "from simile.player.lifespan import running\n"
    app = create_app(make_package(files))
    app.state.world = World(Clock(NOW))
    x, y, map = AT_THE_LOCKERS.x, AT_THE_LOCKERS.y, AT_THE_LOCKERS.map

    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        states = states_from(ws)
        ws.send_json({"type": "player_move", "position": {"x": x, "y": y, "map": map}})
        movement, deadline = movement_of(app), time.monotonic() + 2
        while client.portal.call(movement.entities).get(PLAYER_ID) != AT_THE_LOCKERS:
            assert time.monotonic() < deadline, "the server never had the player there"
            time.sleep(0.001)

        ws.send_json({"type": "stash", "item": "lamp", "action": "store"})
        state = state_where(states, stashed)
        assert stashed(state) == ["lamp"]
        assert state["player"]["items"] == []

        ws.send_json({"type": "stash", "item": "lamp", "action": "take"})
        state = state_where(states, lambda state: not stashed(state))
        assert [item["id"] for item in state["player"]["items"]] == ["lamp"]
