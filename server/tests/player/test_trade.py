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
from simile.protocol import Buyer, Offer
from simile.schema import PLAYER_ID, Item, ItemKind, Player, Sale, lamp
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
        prices={"copper_wire": ECONOMY.salvage["copper_wire"], "scrap_steel": 5, "lamp": 12},
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


@pytest.mark.parametrize("item", ["pork_bun", "odd_bolt", "servo_motor", None])
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


PLUG = Item(id="usb_c_connector", kind=ItemKind.PART, name="USB-C connector", weight=0.1)
LENS = Item(id="infrared_lens", kind=ItemKind.PART, name="Infrared lens", weight=0.2)


def test_every_part_a_recipe_uses_up_sells() -> None:
    from simile.clinic.config import DEFAULT_CONFIG as CLINIC

    used = {id for recipe in CLINIC.recipes.values() for id in recipe.parts}
    assert used <= set(ECONOMY.salvage) | set(ECONOMY.parts)


@pytest.mark.parametrize(("at", "place"), [(STALL, "scrap_stall"), (CLINIC, "clinic")])
def test_a_part_sold_is_bought_back_at_twice_what_it_fetched(at: Point, place: str) -> None:
    platform = Platform(Player(money=20, items=[PLUG, WIRE]))
    platform.stand(at)

    assert platform.trade.buyer().prices == {"usb_c_connector": 12, "copper_wire": 6}
    assert platform.trade.sell(None)
    assert platform.player.money == 38
    assert platform.player.sales == [Sale(item=PLUG, place=place, price=12)]
    assert platform.trade.buyer().stock == [Offer(item=PLUG, price=24)]

    assert platform.trade.buy("usb_c_connector")

    assert platform.player.items == [PLUG]
    assert platform.player.money == 14
    assert platform.player.sales == []
    assert platform.trade.buyer().stock == []
    bought = platform.economy.ledger.entries[-1]
    assert (bought.kind, bought.payer, bought.payee, bought.place, bought.amount) == (
        Kind.PURCHASE,
        PLAYER,
        OUTSIDE,
        place,
        24,
    )
    assert platform.balanced()


def test_only_what_was_sold_is_on_offer_and_only_where_it_was_sold() -> None:
    platform = Platform(Player(money=100, items=[PLUG, WIRE]))
    platform.stand(STALL)
    platform.trade.sell(None)

    assert [offer.item for offer in platform.trade.buyer().stock] == [PLUG]
    assert not platform.trade.buy("copper_wire")
    assert not platform.trade.buy("infrared_lens")
    platform.stand(CLINIC)
    assert platform.trade.buyer().stock == []
    assert not platform.trade.buy("usb_c_connector")
    platform.stand(Point(40, 15, "metro"))
    assert not platform.trade.buy("usb_c_connector")
    assert platform.player.items == []
    assert platform.player.money == 118


def test_stock_is_cheapest_first_and_buying_takes_the_cheapest() -> None:
    dear = Sale(item=PLUG, place="scrap_stall", price=12)
    cheap = Sale(item=PLUG, place="scrap_stall", price=5)
    lens = Sale(item=LENS, place="scrap_stall", price=8)
    platform = Platform(Player(money=100, items=[], sales=[dear, lens, cheap]))
    platform.stand(STALL)

    assert platform.trade.buyer().stock == [
        Offer(item=PLUG, price=10),
        Offer(item=LENS, price=16),
        Offer(item=PLUG, price=24),
    ]
    assert platform.trade.buy("usb_c_connector")
    assert platform.player.money == 90
    assert platform.player.sales == [dear, lens]


def test_selling_one_part_by_id_keeps_it_for_them() -> None:
    platform = Platform(Player(items=[PLUG, PLUG]))
    platform.stand(STALL)

    assert platform.trade.sell("usb_c_connector")

    assert platform.player.items == [PLUG]
    assert platform.player.sales == [Sale(item=PLUG, place="scrap_stall", price=12)]


def test_they_buy_back_nothing_they_cannot_pay_for_or_carry() -> None:
    sale = Sale(item=PLUG, place="scrap_stall", price=12)
    broke = Platform(Player(money=23.5, items=[], sales=[sale]))
    broke.stand(STALL)
    laden = Platform(Player(money=100, items=[STEEL, STEEL], carry_limit=9, sales=[sale]))
    laden.stand(STALL)

    assert not broke.trade.buy("usb_c_connector")
    assert not laden.trade.buy("usb_c_connector")

    for platform in (broke, laden):
        assert platform.player.sales == [sale]
        assert platform.economy.ledger.entries == []


def test_salvage_a_recipe_uses_up_is_kept_but_other_salvage_is_not() -> None:
    coil = Item(id="copper_coil", kind=ItemKind.SALVAGE, name="Copper coil", weight=1.0)
    platform = Platform(Player(money=0, items=[coil, WIRE]))
    platform.stand(STALL)

    assert platform.trade.sell(None)

    assert platform.player.sales == [Sale(item=coil, place="scrap_stall", price=7)]
    assert platform.trade.buyer().stock == [Offer(item=coil, price=14)]


def test_a_part_is_worth_less_than_the_fitting_it_goes_into() -> None:
    from simile.clinic.config import DEFAULT_CONFIG as CLINIC

    prices = ECONOMY.salvage | ECONOMY.parts
    for recipe in CLINIC.recipes.values():
        assert sum(prices[id] * n for id, n in recipe.parts.items()) < recipe.credits


def test_the_salvage_kept_is_what_the_sewers_finds_hold() -> None:
    from simile.street.sewers import FINDS

    assert ECONOMY.kept == {item for find in FINDS for item in find.items}


def test_the_scrap_trader_buys_the_lamp_and_sells_it_back_off_at_twice_with_its_charge() -> None:
    held = lamp().model_copy(update={"charge": 0.4, "on": True})
    platform = Platform(Player(money=13, items=[WIRE, held]))
    platform.stand(STALL)

    assert platform.trade.buyer().prices["lamp"] == ECONOMY.lamp["scrap_stall"] == 12
    assert platform.trade.sell("lamp")

    assert platform.player.items == [WIRE]
    assert platform.player.money == 25
    kept = held.model_copy(update={"on": False})
    assert platform.player.sales == [Sale(item=kept, place="scrap_stall", price=12)]
    assert platform.trade.buyer().prices == {"copper_wire": 6}
    assert platform.trade.buyer().stock == [Offer(item=kept, price=24)]

    assert platform.trade.buy("lamp")

    assert platform.player.items == [WIRE, kept]
    assert platform.player.money == 1
    assert platform.player.sales == []
    sold = platform.economy.ledger.entries[0]
    assert (sold.kind, sold.payer, sold.payee, sold.amount) == (Kind.SALVAGE, OUTSIDE, PLAYER, 12)
    assert platform.balanced()


def test_selling_everything_keeps_the_lamp() -> None:
    platform = Platform(Player(items=[lamp(), WIRE]))
    platform.stand(STALL)

    assert platform.trade.sell(None)

    assert platform.player.items == [lamp()]
    assert platform.player.sales == []


def test_only_the_scrap_trader_buys_the_lamp() -> None:
    platform = Platform(Player(items=[lamp()]))
    platform.stand(CLINIC)

    assert platform.trade.buyer().prices == {}
    assert not platform.trade.sell("lamp")
    assert platform.player.items == [lamp()]


def test_a_save_without_a_lamp_loads_without_one_and_one_sold_loads_kept() -> None:
    sale = Sale(item=lamp().model_copy(update={"charge": 0.3}), place="scrap_stall", price=12)
    player = Player(items=[WIRE], sales=[sale])

    loaded = Player.model_validate_json(player.model_dump_json())

    assert loaded.items == [WIRE]
    assert loaded.sales == [sale]
    assert Player.model_validate_json('{"items": []}').items == []
