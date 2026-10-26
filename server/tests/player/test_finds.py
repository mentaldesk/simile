from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime

from simile.behaviour import Behaviour
from simile.clinic.config import DEFAULT_CONFIG as CLINIC
from simile.economy import PLAYER, Kind
from simile.economy.economy import Economy
from simile.memory import MemoryStore
from simile.npc import load_npcs
from simile.player.finds import Finds
from simile.player.machines import Machines
from simile.player.pickups import Pickups
from simile.schema import (
    PLAYER_ID,
    Bionic,
    Body,
    Interactable,
    InteractableKind,
    Item,
    MapTile,
    Mind,
    Pile,
    Player,
    Tile,
    TileArea,
)
from simile.sim import Clock, FakeWallClock, World
from simile.street.finds import COPPER_WIRE, USB_C_CONNECTOR
from simile.street.metro import DEAD_TERMINAL, LIFT
from simile.street.village import SHELF
from simile.world import Movement, Point
from simile.world.map import TownMap, load_maps

NOW = datetime(2026, 1, 1, 12, tzinfo=UTC)
MAPS = load_maps()
DATAJACK = Body(vertebra=Bionic.DATAJACK)
BENCH = Point(5, 2, "maker_space_floor_0")
LOFT_SHELF = Point(12, 2, "maker_space_floor_2")
TERMINAL = Point(104, 15, "metro")
ANVIL = Item(id="anvil", kind="salvage", name="Anvil", weight=8.5)


def holding(map_id: str, thing_id: str, **update: object) -> dict[str, TownMap]:
    """The maps, with the interactable `thing_id` changed by `update`."""
    town = MAPS[map_id]
    things = tuple(
        thing.model_copy(update=update) if thing.id == thing_id else thing
        for thing in town.interactables
    )
    return {**MAPS, map_id: replace(town, interactables=things)}


class Searching:
    def __init__(self, player: Player | None = None, maps: Mapping[str, TownMap] = MAPS) -> None:
        world = World(Clock(NOW), FakeWallClock())
        self.movement = Movement(maps, world.bus)
        npcs = load_npcs()[:2]
        behaviour = Behaviour(
            world.clock, world.bus, self.movement, npcs, MemoryStore(":memory:"), seed=0
        )
        self.player = player or Player()
        economy = Economy(world.clock, behaviour, player=self.player)
        self.pickups = Pickups(self.player, self.movement, economy, world.clock)
        self.economy = economy
        self.finds = Finds(
            self.player, self.movement, known=lambda: CLINIC.recipes, find=economy.find
        )
        self.clues: list[str] = []
        self.machines = Machines(
            self.player,
            self.movement,
            lambda jack: self.clues.append(jack.id),
            lambda: {DEAD_TERMINAL},
        )

    def e(self, at: Point) -> None:
        self.movement.track(PLAYER_ID, at)
        self.pickups.pick_up([self.machines.claim, self.finds.claim])


def test_aris_bench_teaches_the_datajack_once() -> None:
    searching = Searching()

    searching.e(BENCH)
    searching.e(BENCH)

    assert searching.player.mind.recipes == [Bionic.DATAJACK]
    assert searching.player.searched == ["maker_space_bench"]
    assert searching.player.items == Player().items


def test_searching_takes_what_it_holds_and_it_holds_nothing_after() -> None:
    searching = Searching()

    searching.e(LOFT_SHELF)
    searching.e(LOFT_SHELF)

    assert [item.id for item in searching.player.items] == [
        "lamp",
        USB_C_CONNECTOR.id,
        "copper_wire",
    ]
    assert searching.player.searched == [SHELF]
    assert searching.player.mind == Mind()


def test_the_money_in_a_thing_is_found_through_the_ledger_once() -> None:
    searching = Searching()
    mattress = Point(2, 2, "house_2_floor_1")

    searching.e(mattress)
    searching.e(mattress)

    ledger = searching.economy.ledger
    assert searching.player.money == 10
    assert [(e.kind, e.amount, e.payee, e.place) for e in ledger.entries] == [
        (Kind.FOUND, 10, PLAYER, "house_2_bed")
    ]
    assert searching.player.searched == ["house_2_bed"]


def test_what_doesnt_fit_is_left_where_they_stand() -> None:
    player = Player()
    player.items = [*player.items, ANVIL]
    searching = Searching(player)

    searching.e(Point(12.2, 2, LOFT_SHELF.map))

    assert [item.id for item in player.items] == ["lamp", "anvil", USB_C_CONNECTOR.id]
    assert player.left == [Pile(at=MapTile(map=LOFT_SHELF.map, x=12, y=2), items=[COPPER_WIRE])]
    assert player.searched == [SHELF]


def test_searching_comes_before_a_pile_where_they_stand() -> None:
    player = Player()
    pile = Pile(at=MapTile(map=LOFT_SHELF.map, x=12, y=2), items=[USB_C_CONNECTOR])
    player.left = [pile]
    searching = Searching(player)

    searching.e(LOFT_SHELF)

    assert player.searched == [SHELF]
    assert player.left == [pile]

    searching.e(LOFT_SHELF)

    assert player.left == []


def test_a_jack_holding_nothing_is_never_searched_and_gives_its_clue_on_the_first_e() -> None:
    searching = Searching(Player(body=DATAJACK))

    searching.e(TERMINAL)
    searching.e(Point(100, 15, "metro"))

    assert searching.clues == [DEAD_TERMINAL]
    assert searching.player.searched == []


def test_a_jack_holding_something_gives_it_first_and_its_clue_on_the_second_e() -> None:
    maps = holding("metro", DEAD_TERMINAL, items=[COPPER_WIRE], teaches=Bionic.INFRARED_EYE)
    searching = Searching(Player(body=DATAJACK), maps)

    searching.e(TERMINAL)

    assert searching.clues == []
    assert searching.player.searched == [DEAD_TERMINAL]
    assert searching.player.mind.recipes == [Bionic.INFRARED_EYE]
    assert searching.player.items[-1] == COPPER_WIRE

    searching.e(TERMINAL)

    assert searching.clues == [DEAD_TERMINAL]
    assert searching.player.searched == [DEAD_TERMINAL]


def test_a_jack_holding_only_money_is_searched_with_the_datajack() -> None:
    maps = holding("metro", DEAD_TERMINAL, money=20.0)
    searching = Searching(Player(body=DATAJACK), maps)

    searching.e(TERMINAL)

    assert (searching.player.money, searching.player.searched) == (20, [DEAD_TERMINAL])
    assert searching.clues == []


def test_a_jack_is_searched_only_with_the_datajack() -> None:
    maps = holding("metro", LIFT, teaches=Bionic.INFRARED_EYE)
    searching = Searching(Player(), maps)

    searching.e(Point(100, 15, "metro"))

    assert searching.player.searched == []
    assert searching.player.mind == Mind()


def test_they_learn_only_a_recipe_there_is() -> None:
    searching = Searching()
    searching.finds.known = lambda: {Bionic.SPRING_FEET: CLINIC.recipes[Bionic.SPRING_FEET]}

    assert not searching.finds.learn(Bionic.INFRARED_EYE)
    assert searching.finds.learn(Bionic.SPRING_FEET)
    assert not searching.finds.learn(Bionic.SPRING_FEET)
    assert searching.player.mind.recipes == [Bionic.SPRING_FEET]


def test_a_recipe_they_know_is_still_searched_for_its_parts() -> None:
    searching = Searching(Player(mind=Mind(recipes=[Bionic.DATAJACK], sold=[Bionic.DATAJACK])))

    searching.e(BENCH)

    assert searching.player.mind == Mind(recipes=[Bionic.DATAJACK], sold=[Bionic.DATAJACK])
    assert searching.player.searched == ["maker_space_bench"]


def test_the_doctor_tells_them_the_power_cells_recipe_as_they_walk_in() -> None:
    searching = Searching()
    searching.movement.track(PLAYER_ID, Point(85, 15, "metro"))
    searching.finds.tick(1.0)

    assert searching.player.mind == Mind()

    searching.movement.track(PLAYER_ID, Point(4, 2, "clinic_floor_0"))
    searching.finds.tick(1.0)
    searching.finds.tick(1.0)

    assert searching.player.mind.recipes == [Bionic.POWER_CELL]


def test_only_a_searchable_or_a_jack_is_searched() -> None:
    plug = Interactable(
        id="plug",
        label="Plug",
        kind=InteractableKind.PLUG,
        map=BENCH.map,
        area=TileArea(x=5, y=2, width=1, height=1),
        stand=[Tile(x=5, y=2)],
    )
    town = MAPS[BENCH.map]
    maps = {**MAPS, BENCH.map: replace(town, interactables=(plug,))}
    searching = Searching(maps=maps)

    searching.e(BENCH)

    assert searching.player.searched == []
