from datetime import UTC, datetime

import pytest

from simile.behaviour import Behaviour
from simile.economy import DEFAULT_CONFIG as ECONOMY
from simile.economy import OUTSIDE, PLAYER, Kind
from simile.economy.economy import Economy
from simile.memory import MemoryStore
from simile.npc import load_npcs
from simile.player.config import DEFAULT_CONFIG, SALVAGE
from simile.player.trade import Trade, counted
from simile.protocol import Buyer
from simile.schema import PLAYER_ID, Item, ItemKind, Player, lamp
from simile.sim import Clock, FakeWallClock, World
from simile.world import Movement, Point
from simile.world.map import load_maps

NOW = datetime(2026, 1, 1, 12, tzinfo=UTC)
WIRE, STEEL, BOARD = (SALVAGE[f"metro_salvage_{n}"].item for n in (1, 2, 3))
BUN = Item(id="pork_bun", kind=ItemKind.FOOD, name="Pork bun", weight=0.2)
ODD = Item(id="odd_bolt", kind=ItemKind.SALVAGE, name="Odd bolt", weight=0.1)


MAPS = load_maps()
STALL = Point(26, 15, "metro")
"""The scrap trader's spot, by their stall on the metro's platform."""
CLINIC = Point(6, 2, "clinic_floor_0")
"""The doctor's spot in the clinic."""


class Platform:
    def __init__(self, player: Player) -> None:
        world = World(Clock(NOW), FakeWallClock())
        self.movement = Movement(MAPS, world.bus)
        behaviour = Behaviour(
            world.clock,
            world.bus,
            self.movement,
            load_npcs()[:2],
            MemoryStore(":memory:"),
            seed=0,
        )
        self.player = player
        self.start = player.money
        self.economy = Economy(world.clock, behaviour, player=player)
        self.trade = Trade(player, self.movement, self.economy, world.clock)

    def stand(self, at: Point) -> None:
        self.movement.track(PLAYER_ID, at)

    def balanced(self) -> bool:
        ledger = self.economy.ledger
        gained = ledger.net(PLAYER) == pytest.approx(self.player.money - self.start)
        return gained and ledger.gap(self.economy.money) == pytest.approx(0)


def test_every_salvage_lying_about_has_a_price() -> None:
    items = [salvage.item for salvage in DEFAULT_CONFIG.salvage.values()]
    assert {item.id for item in items} <= set(ECONOMY.salvage)
    assert all(item.kind is ItemKind.SALVAGE for item in items)


def test_the_scrap_trader_offers_the_economys_price_for_the_salvage_they_carry() -> None:
    platform = Platform(Player(items=[lamp(), WIRE, BUN, STEEL, WIRE, ODD]))
    platform.stand(STALL)

    assert platform.trade.buyer() == Buyer(
        place="scrap_stall",
        name="The scrap trader's stall",
        prices={"copper_wire": ECONOMY.salvage["copper_wire"], "scrap_steel": 5},
    )


def test_a_buyer_with_nothing_to_buy_still_says_it_buys() -> None:
    platform = Platform(Player())
    platform.stand(CLINIC)

    assert platform.trade.buyer() == Buyer(place="clinic", name="The Clinic", prices={})


def test_no_buyer_anywhere_else() -> None:
    platform = Platform(Player(items=[WIRE]))

    assert platform.trade.buyer() is None
    platform.stand(Point(40, 15, "metro"))
    assert platform.trade.buyer() is None
    platform.stand(Point(12, 15, "kapok_walk"))
    assert platform.trade.buyer() is None
    assert not platform.trade.sell(None)
    assert platform.player.items == [WIRE]


@pytest.mark.parametrize(
    ("at", "place"),
    [(STALL, "scrap_stall"), (Point(24, 15, "metro"), "scrap_stall"), (CLINIC, "clinic")],
    ids=["by_the_stall", "at_its_end", "clinic"],
)
def test_selling_everything_it_buys_pays_its_prices_through_the_ledger(
    at: Point, place: str
) -> None:
    platform = Platform(Player(money=3, items=[lamp(), WIRE, BUN, STEEL, BOARD, ODD]))
    platform.stand(at)

    assert platform.trade.sell(None)

    assert platform.player.items == [lamp(), BUN, ODD]
    assert platform.player.money == 3 + 6 + 5 + 8
    sales = platform.economy.ledger.entries
    assert [(sale.kind, sale.payer, sale.payee, sale.place) for sale in sales] == [
        (Kind.SALVAGE, OUTSIDE, PLAYER, place)
    ] * 3
    assert [sale.amount for sale in sales] == [6, 5, 8]
    assert platform.balanced()


def test_selling_one_by_id_sells_only_one() -> None:
    platform = Platform(Player(items=[WIRE, STEEL, WIRE]))
    platform.stand(STALL)

    assert platform.trade.sell("copper_wire")

    assert platform.player.items == [STEEL, WIRE]
    assert platform.player.money == 6
    assert platform.trade.buyer() == Buyer(
        place="scrap_stall",
        name="The scrap trader's stall",
        prices={"copper_wire": 6, "scrap_steel": 5},
    )
    assert platform.balanced()


@pytest.mark.parametrize("item", ["lamp", "pork_bun", "odd_bolt", "servo_motor", None])
def test_nothing_sells_that_the_buyer_does_not_buy_or_they_do_not_carry(item: str | None) -> None:
    platform = Platform(Player(money=3, items=[lamp(), BUN, ODD]))
    platform.stand(STALL)

    assert not platform.trade.sell(item)

    assert platform.player.items == [lamp(), BUN, ODD]
    assert platform.player.money == 3
    assert platform.economy.ledger.entries == []


def test_what_they_sold_is_said_once_a_kind() -> None:
    assert counted([WIRE, BOARD, WIRE]) == "Copper wire ×2, Circuit board"
    assert counted([STEEL]) == "Scrap steel"
