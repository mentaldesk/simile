from dataclasses import replace
from datetime import UTC, datetime

import pytest

from simile.behaviour import Behaviour
from simile.economy import DEFAULT_CONFIG as ECONOMY
from simile.economy import OUTSIDE, PLAYER, Kind
from simile.economy.economy import Economy
from simile.memory import MemoryStore
from simile.npc import load_npcs
from simile.player.config import DEFAULT_CONFIG, SALVAGE
from simile.player.trade import Trade
from simile.protocol import Buyer
from simile.schema import (
    PLAYER_ID,
    Item,
    ItemKind,
    Location,
    LocationKind,
    Player,
    Tile,
    TileArea,
    lamp,
)
from simile.sim import Clock, FakeWallClock, World
from simile.world import Movement, Point
from simile.world.map import load_maps

NOW = datetime(2026, 1, 1, 12, tzinfo=UTC)
WIRE, STEEL, BOARD = (SALVAGE[f"metro_salvage_{n}"] for n in (1, 2, 3))
BUN = Item(id="pork_bun", kind=ItemKind.FOOD, name="Pork bun", weight=0.2)
ODD = Item(id="odd_bolt", kind=ItemKind.SALVAGE, name="Odd bolt", weight=0.1)


def place(id: str, name: str, x: int) -> Location:
    area = TileArea(x=x, y=13, width=5, height=3)
    return Location(
        id=id,
        name=name,
        kind=LocationKind.AMENITY,
        map="kapok_walk",
        area=area,
        entry=Tile(x=x, y=15),
    )


MAPS = load_maps()
STREET = MAPS["kapok_walk"]
STALLS = (place("scrap_stall", "The scrap trader's stall", 20), place("clinic", "The Clinic", 40))
WITH_STALLS = MAPS | {"kapok_walk": replace(STREET, locations=(*STREET.locations, *STALLS))}


class Platform:
    def __init__(self, player: Player) -> None:
        world = World(Clock(NOW), FakeWallClock())
        self.movement = Movement(WITH_STALLS, world.bus)
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

    def stand(self, x: float) -> None:
        self.movement.track(PLAYER_ID, Point(x, 15, "kapok_walk"))

    def balanced(self) -> bool:
        ledger = self.economy.ledger
        gained = ledger.net(PLAYER) == pytest.approx(self.player.money - self.start)
        return gained and ledger.gap(self.economy.money) == pytest.approx(0)


def test_every_salvage_lying_about_has_a_price() -> None:
    assert {item.id for item in DEFAULT_CONFIG.salvage.values()} <= set(ECONOMY.salvage)
    assert all(item.kind is ItemKind.SALVAGE for item in DEFAULT_CONFIG.salvage.values())


def test_the_scrap_trader_offers_the_economys_price_for_the_salvage_they_carry() -> None:
    platform = Platform(Player(items=[lamp(), WIRE, BUN, STEEL, WIRE, ODD]))
    platform.stand(22)

    assert platform.trade.buyer() == Buyer(
        place="scrap_stall",
        name="The scrap trader's stall",
        prices={"copper_wire": ECONOMY.salvage["copper_wire"], "scrap_steel": 5},
    )


def test_a_buyer_with_nothing_to_buy_still_says_it_buys() -> None:
    platform = Platform(Player())
    platform.stand(42)

    assert platform.trade.buyer() == Buyer(place="clinic", name="The Clinic", prices={})


def test_no_buyer_anywhere_else() -> None:
    platform = Platform(Player(items=[WIRE]))

    assert platform.trade.buyer() is None
    platform.stand(30)
    assert platform.trade.buyer() is None
    assert not platform.trade.sell(None)
    assert platform.player.items == [WIRE]


@pytest.mark.parametrize("x", [21, 41], ids=["scrap_stall", "clinic"])
def test_selling_everything_it_buys_pays_its_prices_through_the_ledger(x: float) -> None:
    platform = Platform(Player(money=3, items=[lamp(), WIRE, BUN, STEEL, BOARD, ODD]))
    platform.stand(x)
    buyer = platform.trade.buyer()
    assert buyer is not None

    assert platform.trade.sell(None)

    assert platform.player.items == [lamp(), BUN, ODD]
    assert platform.player.money == 3 + 6 + 5 + 8
    sales = platform.economy.ledger.entries
    assert [(sale.kind, sale.payer, sale.payee, sale.place) for sale in sales] == [
        (Kind.SALVAGE, OUTSIDE, PLAYER, buyer.place)
    ] * 3
    assert [sale.amount for sale in sales] == [6, 5, 8]
    assert platform.balanced()


def test_selling_one_by_id_sells_only_one() -> None:
    platform = Platform(Player(items=[WIRE, STEEL, WIRE]))
    platform.stand(22)

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
    platform.stand(22)

    assert not platform.trade.sell(item)

    assert platform.player.items == [lamp(), BUN, ODD]
    assert platform.player.money == 3
    assert platform.economy.ledger.entries == []
