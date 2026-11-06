from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from simile.behaviour import Behaviour
from simile.machines.workshop import MACHINES, Offer, Workshop, register_offers
from simile.memory import MemoryStore
from simile.npc import load_npcs
from simile.persistence import WorldStore, capture
from simile.schema import (
    PLAYER_ID,
    InteractableKind,
    Item,
    ItemKind,
    Machine,
    MachineKind,
    MachineState,
    Material,
    Player,
    Product,
    lamp,
)
from simile.sim import Clock, FakeWallClock, World
from simile.street.sewers import APEX_BOARD, SCRAP
from simile.street.village import LOCKERS
from simile.world import Movement, Point
from simile.world.map import load_maps

MAPS = load_maps()
PRINTER, RECYCLER = "printer_3d", "recycler"
AT_THE_PRINTER = Point(9, 2, "maker_space_floor_0")
ROUNDS = Item(
    id="plastic_rounds",
    kind=ItemKind.ROUNDS,
    name="Rounds",
    weight=0.01,
    amount=6.0,
    material=Material.PLASTIC,
)


def part(id: str) -> Item:
    return Item(id=id, kind=ItemKind.PART, name=id.replace("_", " "), weight=0.5)


SHEET, ACTUATOR, WIRE = part("metal_sheet"), part("linear_actuator"), part("copper_wire")
THE_PARTS = [SHEET, ACTUATOR, WIRE, WIRE]
MakePackage = Callable[[dict[str, str]], str]


def workshop(player: Player, at: Point | None = AT_THE_PRINTER) -> tuple[Workshop, list[Machine]]:
    world = World(Clock(datetime(2026, 1, 1, 12, tzinfo=UTC)), FakeWallClock())
    movement = Movement(MAPS, world.bus)
    if at is not None:
        movement.track(PLAYER_ID, at)
    changed: list[Machine] = []
    return Workshop(player, movement, changed.append), changed


def test_both_machines_start_broken_listing_what_they_need() -> None:
    shop, _ = workshop(Player())

    assert shop.machines() == [
        Machine(
            id=PRINTER,
            kind=MachineKind.PRINTER,
            state=MachineState.BROKEN,
            parts={"metal_sheet": 1, "linear_actuator": 1, "copper_wire": 2},
        ),
        Machine(
            id=RECYCLER,
            kind=MachineKind.RECYCLER,
            state=MachineState.BROKEN,
            parts={"apex_board": 1, "old_battery": 2},
        ),
    ]


def test_the_recyclers_parts_are_found_in_the_sewers() -> None:
    parts = MACHINES[RECYCLER].parts

    assert APEX_BOARD.id in parts and "old_battery" in SCRAP
    assert parts.keys() == {APEX_BOARD.id, "old_battery"}


def test_repairing_takes_only_the_parts_and_tells_the_client() -> None:
    spare = WIRE.model_copy()
    player = Player(items=[lamp(), SHEET, WIRE, ACTUATOR, WIRE, spare])
    shop, changed = workshop(player)

    assert shop.repair(PRINTER)

    assert player.items == [lamp(), spare]
    assert player.repaired == [PRINTER]
    fixed = Machine(id=PRINTER, kind=MachineKind.PRINTER, state=MachineState.WORKING)
    assert changed == [fixed]
    assert shop.machine(PRINTER) == fixed


@pytest.mark.parametrize(
    ("items", "short"),
    [
        ([], {"metal_sheet": 1, "linear_actuator": 1, "copper_wire": 2}),
        ([SHEET, ACTUATOR, WIRE], {"copper_wire": 1}),
    ],
)
def test_repairing_without_every_part_changes_nothing(
    items: list[Item], short: dict[str, int]
) -> None:
    player = Player(items=items)
    shop, changed = workshop(player)

    assert shop.missing(PRINTER) == short
    assert not shop.repair(PRINTER)

    assert player.items == items and player.repaired == [] and changed == []


@pytest.mark.parametrize(
    "at", [None, Point(8, 2, "maker_space_floor_0"), Point(9, 2, "maker_space_floor_1")]
)
def test_repairing_needs_them_at_the_machine(at: Point | None) -> None:
    player = Player(items=THE_PARTS)
    shop, _ = workshop(player, at)

    assert not shop.repair(PRINTER)
    assert player.items == THE_PARTS and player.repaired == []


def test_a_machine_is_repaired_once_and_an_unknown_one_never() -> None:
    player = Player(items=[*THE_PARTS, *THE_PARTS])
    shop, changed = workshop(player)

    assert shop.repair(PRINTER)
    assert not shop.repair(PRINTER)
    assert not shop.repair("laser_cutter")

    assert player.items == THE_PARTS and len(changed) == 1


def test_a_repair_survives_a_save_and_reload(tmp_path: Path) -> None:
    player = Player(items=[lamp(), *THE_PARTS])
    shop, _ = workshop(player)
    assert shop.repair(PRINTER)

    world = World(Clock(datetime(2026, 1, 1, 12, tzinfo=UTC)), FakeWallClock())
    behaviour = Behaviour(world.clock, world.bus, Movement(MAPS, world.bus), load_npcs(), seed=0)
    path = tmp_path / "simile.db"
    with MemoryStore(path) as memory, WorldStore(memory) as store:
        store.save(capture(behaviour, player=player))
    with MemoryStore(path) as memory, WorldStore(memory) as store:
        loaded = store.load()

    assert loaded is not None and loaded.player.items == [lamp()]
    reloaded, _ = workshop(loaded.player)
    assert reloaded.machine(PRINTER).state is MachineState.WORKING
    assert reloaded.machine(RECYCLER).state is MachineState.BROKEN


def offer(made: list[Player] | None = None) -> Offer:
    def make(player: Player) -> bool:
        if made is not None:
            made.append(player)
        return made is not None

    return Offer(Product(item=ROUNDS, uses=Material.PLASTIC, cost=2), make)


def test_only_a_working_machine_lists_what_its_offered_and_makes_it() -> None:
    made: list[Player] = []
    player = Player(items=THE_PARTS)
    shop, _ = workshop(player)
    shop.offer(PRINTER, offer(made))

    assert shop.machine(PRINTER).makes == []
    assert not shop.make(PRINTER, ROUNDS.id) and made == []

    shop.repair(PRINTER)

    assert shop.machine(PRINTER).makes == [offer().product]
    assert not shop.make(PRINTER, "pistol")
    assert shop.make(PRINTER, ROUNDS.id) and made == [player]


def test_making_needs_them_at_the_machine_and_says_when_it_cant() -> None:
    player = Player(repaired=[PRINTER])
    away, _ = workshop(player, Point(8, 2, "maker_space_floor_0"))
    away.offer(PRINTER, offer([]))
    assert not away.make(PRINTER, ROUNDS.id)

    there, _ = workshop(player)
    there.offer(PRINTER, offer())
    assert not there.make(PRINTER, ROUNDS.id)


def test_an_offer_can_change_with_what_they_carry_and_is_sent_when_it_does() -> None:
    def rounds(player: Player) -> Product | None:
        if not player.items:
            return None
        return Product(item=ROUNDS, uses="scrap", cost=len(player.items))

    player = Player(items=[], repaired=[PRINTER])
    shop, changed = workshop(player)
    shop.offer(PRINTER, Offer(rounds, lambda player: True))
    shop.update()
    assert shop.machine(PRINTER).makes == [] and changed == []
    assert not shop.make(PRINTER, ROUNDS.id)

    player.items = [WIRE, WIRE]
    shop.tick(0.1)
    shop.tick(0.1)

    assert [machine.makes[0].cost for machine in changed] == [2]
    assert shop.make(PRINTER, ROUNDS.id)


def test_offering_on_a_machine_that_isnt_one_fails_loudly() -> None:
    with pytest.raises(KeyError):
        workshop(Player())[0].offer("laser_cutter", offer())


def test_a_new_module_beside_it_registers_its_offers(make_package: MakePackage) -> None:
    package = make_package(
        {
            "printer.py": "def register(workshop):\n    workshop.registered = True\n",
            "plain.py": "VALUE = 1\n",
        }
    )
    shop, _ = workshop(Player())

    register_offers(shop, package)

    assert shop.registered  # type: ignore[attr-defined]


def test_the_real_package_registers_without_failing() -> None:
    register_offers(workshop(Player())[0])


@pytest.mark.parametrize(
    ("id", "floor", "x"),
    [(PRINTER, 0, 9), (RECYCLER, 0, 1), (LOCKERS, 2, 7)],
)
def test_the_machines_and_the_lockers_stand_in_the_maker_space(id: str, floor: int, x: int) -> None:
    town = MAPS[f"maker_space_floor_{floor}"]
    [item] = [item for item in town.interactables if item.id == id]
    [stand] = item.stand
    ends = {
        (end.x, end.y)
        for door in town.doors
        for end in (door.outside, door.inside)
        if end.map == town.id
    }

    assert item.kind is InteractableKind.MACHINE
    assert stand.x == x and town.standing(stand.x, stand.y)
    assert (stand.x, stand.y) not in ends, "E would take the door instead"
