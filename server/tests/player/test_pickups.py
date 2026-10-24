from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from simile.behaviour import Behaviour
from simile.economy import OUTSIDE, PLAYER, Kind
from simile.economy.economy import Economy
from simile.memory import MemoryStore
from simile.npc import load_npcs
from simile.player.config import DEFAULT_CONFIG, SALVAGE, Salvage
from simile.player.pickups import Pickups
from simile.schema import PLAYER_ID, Item, ItemKind, MapTile, Pile, Player, lamp
from simile.sim import Clock, FakeWallClock, World
from simile.world import Movement, Point
from simile.world.map import Pickup, PickupKind, TownMap, load_maps

NOW = datetime(2026, 1, 1, 12, tzinfo=UTC)
BUN = Item(id="pork_bun", kind=ItemKind.FOOD, name="Pork bun", weight=0.2)
WIRE = SALVAGE["metro_salvage_1"].item
STEEL = SALVAGE["metro_salvage_2"].item
DAY = timedelta(hours=24)
SERVO = Item(id="servo_motor", kind=ItemKind.SALVAGE, name="Servo motor", weight=3.0)
RATION = Item(id="ration_pack", kind=ItemKind.FOOD, name="Ration pack", weight=0.5)
LYING = (
    Pickup("metro_salvage_1", PickupKind.SALVAGE, "kapok_walk", 20, 15),
    Pickup("metro_salvage_2", PickupKind.SALVAGE, "kapok_walk", 30, 15),
    Pickup("metro_secret_stairwell", PickupKind.SECRET, "kapok_walk", 40, 15, money=25),
    Pickup("metro_secret_alcove", PickupKind.SECRET, "kapok_walk", 50, 15, item=RATION),
    Pickup("metro_secret_cache", PickupKind.SECRET, "kapok_walk", 60, 15, 40, RATION),
)
MAPS = load_maps()
WITH_PICKUPS = {
    id: replace(town, pickups=LYING if id == "kapok_walk" else ()) for id, town in MAPS.items()
}


def at(x: int, *items: Item, money: float = 0) -> Pile:
    return Pile(at=MapTile(map="kapok_walk", x=x, y=15), items=list(items), money=money)


class Tunnels:
    def __init__(self, player: Player | None = None, maps: Mapping[str, TownMap] = WITH_PICKUPS):
        world = World(Clock(NOW), FakeWallClock())
        self.clock = world.clock
        self.movement = Movement(maps, world.bus)
        npcs = load_npcs()[:2]
        behaviour = Behaviour(
            world.clock, world.bus, self.movement, npcs, MemoryStore(":memory:"), seed=0
        )
        self.player = player or Player()
        self.start = self.player.money
        self.economy = Economy(world.clock, behaviour, player=self.player)
        self.pickups = Pickups(self.player, self.movement, self.economy, world.clock)

    def stand(self, x: float, map: str = "kapok_walk", y: float = 15) -> None:
        self.movement.track(PLAYER_ID, Point(x, y, map))

    def balanced(self) -> bool:
        ledger = self.economy.ledger
        gained = ledger.net(PLAYER) == pytest.approx(self.player.money - self.start)
        return gained and ledger.gap(self.economy.money) == pytest.approx(0)


def test_the_maps_salvage_and_secrets_lie_at_their_pickups() -> None:
    assert Tunnels().pickups.piles() == [
        at(20, WIRE),
        at(30, STEEL),
        at(40, money=25),
        at(50, RATION),
        at(60, RATION, money=40),
    ]


def test_picking_up_salvage_takes_it_and_says_when() -> None:
    tunnels = Tunnels()
    tunnels.stand(20.4)

    assert tunnels.pickups.pick_up()

    assert tunnels.player.items == [lamp(), WIRE]
    assert tunnels.player.taken == {"metro_salvage_1": NOW}
    assert at(20, WIRE) not in tunnels.pickups.piles()
    assert not tunnels.pickups.pick_up()
    assert tunnels.player.items == [lamp(), WIRE]


def test_salvage_lies_there_again_a_day_after_it_was_taken() -> None:
    tunnels = Tunnels()
    tunnels.stand(20)
    assert (SALVAGE["metro_salvage_1"].respawn, DEFAULT_CONFIG.respawn) == (None, 24)
    assert tunnels.pickups.pick_up()

    tunnels.clock.now = NOW + DAY - timedelta(seconds=1)
    assert at(20, WIRE) not in tunnels.pickups.piles()
    assert not tunnels.pickups.pick_up()
    tunnels.clock.now = NOW + DAY
    assert at(20, WIRE) in tunnels.pickups.piles()
    assert tunnels.pickups.pick_up()

    assert tunnels.player.items == [lamp(), WIRE, WIRE]
    assert tunnels.player.taken == {"metro_salvage_1": NOW + DAY}
    assert at(20, WIRE) not in tunnels.pickups.piles()


def test_each_salvage_pickup_comes_back_after_its_own_delay() -> None:
    config = DEFAULT_CONFIG.model_copy(
        update={"salvage": SALVAGE | {"metro_salvage_2": Salvage(item=STEEL, respawn=2)}}
    )
    tunnels = Tunnels(Player(taken={"metro_salvage_1": NOW, "metro_salvage_2": NOW}))
    pickups = Pickups(tunnels.player, tunnels.movement, tunnels.economy, tunnels.clock, config)

    tunnels.clock.now = NOW + timedelta(hours=2)

    assert at(20, WIRE) not in pickups.piles()
    assert at(30, STEEL) in pickups.piles()


def test_a_secret_never_comes_back() -> None:
    taken = {"metro_secret_stairwell": NOW, "metro_secret_alcove": NOW}
    tunnels = Tunnels(Player(taken=taken))

    tunnels.clock.now = NOW + 365 * DAY

    assert tunnels.pickups.piles() == [at(20, WIRE), at(30, STEEL), at(60, RATION, money=40)]


def test_salvage_they_cannot_carry_stays_where_it_lies() -> None:
    tunnels = Tunnels(Player(items=[lamp(), SERVO, SERVO], carry_limit=10))
    tunnels.stand(30)

    assert not tunnels.pickups.pick_up()

    assert tunnels.player.taken == {}
    assert at(30, STEEL) in tunnels.pickups.piles()


def test_a_secrets_cash_is_found_through_the_ledger_however_much_they_carry() -> None:
    tunnels = Tunnels(Player(money=12, items=[lamp(), SERVO, SERVO, SERVO]))
    tunnels.stand(40)

    assert tunnels.pickups.pick_up()

    assert tunnels.player.money == 37
    assert tunnels.player.taken == {"metro_secret_stairwell": NOW}
    found = tunnels.economy.ledger.entries[-1]
    assert (found.kind, found.payer, found.payee) == (Kind.FOUND, OUTSIDE, PLAYER)
    assert (found.amount, found.place) == (25, "metro_secret_stairwell")
    assert tunnels.balanced()


def test_a_secret_can_hold_food() -> None:
    tunnels = Tunnels()
    tunnels.stand(49.2)

    assert tunnels.pickups.pick_up()

    assert tunnels.player.items == [lamp(), RATION]
    assert tunnels.economy.ledger.entries == []


def test_what_does_not_fit_of_a_pickup_is_left_there_as_theirs() -> None:
    tunnels = Tunnels(Player(items=[lamp(), SERVO, SERVO, SERVO]))
    tunnels.stand(60)

    assert tunnels.pickups.pick_up()

    assert tunnels.player.money == 40
    assert tunnels.player.taken == {"metro_secret_cache": NOW}
    assert tunnels.player.left == [at(60, RATION)]
    assert at(60, RATION, money=40) not in tunnels.pickups.piles()
    tunnels.player.items = [lamp()]
    assert tunnels.pickups.pick_up()
    assert (tunnels.player.items, tunnels.player.left) == ([lamp(), RATION], [])
    assert tunnels.player.money == 40
    assert tunnels.balanced()


def test_pickups_they_have_taken_stay_taken_after_a_restart() -> None:
    tunnels = Tunnels(Player(taken={"metro_salvage_1": NOW, "metro_secret_stairwell": NOW}))
    tunnels.stand(20)

    assert tunnels.pickups.piles() == [at(30, STEEL), at(50, RATION), at(60, RATION, money=40)]
    assert not tunnels.pickups.pick_up()


def test_the_nearest_pile_in_reach_is_picked_up_first() -> None:
    tunnels = Tunnels(Player(left=[at(21, BUN)]))
    tunnels.stand(20.6)

    assert tunnels.pickups.pick_up()

    assert tunnels.player.items == [lamp(), BUN]
    assert tunnels.player.taken == {}
    assert tunnels.pickups.pick_up()
    assert tunnels.player.items == [lamp(), BUN, WIRE]


def test_every_salvage_pickup_on_the_maps_has_something_set_to_lie_there() -> None:
    on_maps = {
        pickup.id
        for town in MAPS.values()
        for pickup in town.pickups
        if pickup.kind is PickupKind.SALVAGE and pickup.item is None
    }

    assert on_maps == set(SALVAGE)


def test_the_metros_salvage_and_secrets_lie_where_s3_put_them() -> None:
    piles = Tunnels(maps=MAPS).pickups.piles()
    lying = {(pile.at.x, pile.at.y): pile for pile in piles if pile.at.map == "metro"}

    assert {pile.at.map for pile in piles} == {"metro", "sewers"}
    assert sorted(lying) == [
        (8, 7),
        (38, 12),
        (52, 10),
        (61, 8),
        (63, 15),
        (68, 15),
        (83, 15),
        (85, 5),
        (86, 5),
        (106, 12),
        (108, 12),
    ]
    salvage = [
        lying[cell].items for cell in ((38, 12), (63, 15), (68, 15), (85, 5), (83, 15), (108, 12))
    ]
    assert salvage == [[SALVAGE[f"metro_salvage_{n}"].item] for n in range(1, 7)]
    assert sum(item.weight for items in salvage for item in items) == 12.5
    money = (lying[8, 7].money, lying[52, 10].money, lying[106, 12].money, lying[61, 8].money)
    assert money == (25, 40, 60, 60)
    assert lying[86, 5].items == [RATION]


def test_on_the_metro_they_pick_up_salvage_on_the_trains_roof_and_cash_on_the_catwalk() -> None:
    tunnels = Tunnels(maps=MAPS)

    tunnels.stand(38.3, "metro", 12)
    assert tunnels.pickups.pick_up()
    tunnels.stand(52, "metro", 10)
    assert tunnels.pickups.pick_up()

    assert tunnels.player.items == [lamp(), WIRE]
    assert tunnels.player.money == 40
    assert tunnels.player.taken == {"metro_salvage_1": NOW, "metro_secret_catwalk": NOW}
    assert len([pile for pile in tunnels.pickups.piles() if pile.at.map == "metro"]) == 9
    assert tunnels.balanced()


def test_salvage_nothing_is_set_to_lie_at_is_left_out() -> None:
    lost = Pickup("metro_salvage_9", PickupKind.SALVAGE, "kapok_walk", 70, 15)
    maps = WITH_PICKUPS | {"kapok_walk": replace(MAPS["kapok_walk"], pickups=(*LYING, lost))}
    tunnels = Tunnels()

    movement = Movement(maps, World(Clock(NOW)).bus)
    pickups = Pickups(tunnels.player, movement, tunnels.economy, tunnels.clock)

    assert "metro_salvage_9" not in pickups.lying
    assert len(pickups.piles()) == len(LYING)


def test_salvage_the_map_names_lies_there_and_comes_back_after_the_usual_while() -> None:
    sewer = (
        Pickup("sewer_salvage_1", PickupKind.SALVAGE, "kapok_walk", 10, 15, item=SERVO),
        Pickup("metro_salvage_2", PickupKind.SALVAGE, "kapok_walk", 30, 15, item=SERVO),
    )
    maps = WITH_PICKUPS | {"kapok_walk": replace(MAPS["kapok_walk"], pickups=sewer)}
    config = DEFAULT_CONFIG.model_copy(update={"respawn": 6.0})
    tunnels = Tunnels(maps=maps)
    pickups = Pickups(tunnels.player, tunnels.movement, tunnels.economy, tunnels.clock, config)

    assert pickups.piles() == [at(10, SERVO), at(30, SERVO)]
    tunnels.stand(10)
    assert pickups.pick_up()
    assert tunnels.player.items == [lamp(), SERVO]
    tunnels.clock.now = NOW + timedelta(hours=6)
    assert at(10, SERVO) in pickups.piles()


def piles(*at: tuple[str, int]) -> list[Pile]:
    return [Pile(at=MapTile(map=map, x=x, y=15), items=[BUN, WIRE]) for map, x in at]


def test_picking_up_takes_the_nearest_pile_they_left_in_reach() -> None:
    tunnels = Tunnels(Player(left=piles(("kapok_walk", 12), ("kapok_walk", 14))))
    tunnels.stand(13.2)

    assert tunnels.pickups.pick_up()

    assert tunnels.player.items == [lamp(), BUN, WIRE]
    assert tunnels.player.left == piles(("kapok_walk", 12))


def test_picking_up_leaves_what_they_cannot_carry() -> None:
    heavy = [Pile(at=MapTile(map="kapok_walk", x=12, y=15), items=[SERVO, WIRE, BUN])]
    tunnels = Tunnels(Player(items=[lamp(), SERVO, SERVO], carry_limit=9, left=heavy))
    tunnels.stand(12)

    assert tunnels.pickups.pick_up()

    assert tunnels.player.items == [lamp(), SERVO, SERVO, WIRE, BUN]
    assert tunnels.player.load == pytest.approx(8.7)
    assert tunnels.player.left == [heavy[0].model_copy(update={"items": [SERVO]})]


def test_nothing_is_picked_up_with_no_room_for_any_of_it() -> None:
    heavy = [Pile(at=MapTile(map="kapok_walk", x=12, y=15), items=[SERVO])]
    tunnels = Tunnels(Player(items=[lamp(), SERVO, SERVO], carry_limit=8, left=heavy))
    tunnels.stand(12)

    assert not tunnels.pickups.pick_up()
    assert tunnels.player.left == heavy


@pytest.mark.parametrize(
    ("x", "map"), [(13.6, "kapok_walk"), (12, "high_street")], ids=["too_far", "another_map"]
)
def test_nothing_is_picked_up_out_of_reach(x: float, map: str) -> None:
    tunnels = Tunnels(Player(items=[], left=piles(("kapok_walk", 12))))
    tunnels.stand(x, map)

    assert not tunnels.pickups.pick_up()
    assert tunnels.player.items == []
    assert tunnels.player.left == piles(("kapok_walk", 12))


def test_nothing_is_picked_up_before_the_server_knows_where_they_are() -> None:
    assert not Tunnels(Player(left=piles(("kapok_walk", 12)))).pickups.pick_up()
