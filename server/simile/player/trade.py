import logging
from collections import Counter
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING

from starlette.applications import Starlette

from simile.economy import OUTSIDE, PLAYER, Kind
from simile.player.where import here, location
from simile.protocol import Buyer, Offer
from simile.schema import Id, Item, ItemKind, Player, Sale
from simile.sim import Clock
from simile.world.movement import Movement, inside

if TYPE_CHECKING:
    from simile.economy.economy import Economy

logger = logging.getLogger(__name__)

type Keeper = Callable[[Buyer], Buyer]
"""Adds what a keeper at a buyer's place trades besides salvage, such as the clinic's doctor."""


def keepers_of(app: Starlette) -> dict[Id, Keeper]:
    """Each buyer's keeper by place, on `app.state.keepers`, for modules to add theirs."""
    if not hasattr(app.state, "keepers"):
        app.state.keepers = {}
    return app.state.keepers


class Trade:
    """Selling to whoever buys where the player stands, at the economy's prices, and buying back
    the parts it keeps of what they sold it."""

    def __init__(
        self,
        player: Player,
        movement: Movement,
        economy: "Economy",
        clock: Clock,
        keepers: Mapping[Id, Keeper] | None = None,
    ) -> None:
        self.player = player
        self.movement = movement
        self.economy = economy
        """Its `player` is this one, so sales go through its ledger."""
        self.clock = clock
        self.keepers = keepers or {}

    def buyer(self) -> Buyer | None:
        """Who buys where they stand, and what they'd pay for what they carry."""
        at = here(self.movement)
        if at is None:
            return None
        for place in self.economy.config.buyers:
            stall = location(self.movement, place)
            if stall is None or not inside(stall, at):
                continue
            prices = self.economy.offer(place, self.player.items) or {}
            buyer = Buyer(place=place, name=stall.name, prices=prices, stock=self.stock(place))
            keeper = self.keepers.get(place)
            return keeper(buyer) if keeper else buyer
        return None

    def sell(self, item: Id | None) -> bool:
        """Sells one carried item by id, or with None all the buyer buys. Whether they sold any."""
        buyer = self.buyer()
        if buyer is None:
            return False
        kept = list(self.player.items)
        sold = [thing for thing in kept if thing.id in buyer.prices and item in (None, thing.id)]
        if item is not None:
            sold = sold[:1]
        sales = list(self.player.sales)
        for thing in sold:
            if self.economy.sell(buyer.place, thing):
                kept.remove(thing)
                if thing.kind is ItemKind.PART:
                    sales.append(Sale(item=thing, place=buyer.place, price=buyer.prices[thing.id]))
        if len(kept) == len(self.player.items):
            return False
        self.player.items = kept
        self.player.sales = sales
        logger.info("%s  The player sells %s to %s", self.clock, counted(sold), buyer.name)
        return True

    def stock(self, place: Id) -> list[Offer]:
        """The parts the buyer at `place` keeps of what they sold it, at `buy_back` times what it
        paid, cheapest first."""
        back = self.economy.config.buy_back
        return [Offer(item=sale.item, price=sale.price * back) for sale in self._kept(place)]

    def buy(self, item: Id) -> bool:
        """Buys back the cheapest of `item` the buyer where they stand keeps, if they can pay for it
        and carry it. Whether they bought it."""
        buyer = self.buyer()
        if buyer is None:
            return False
        sale = next((sale for sale in self._kept(buyer.place) if sale.item.id == item), None)
        if sale is None:
            return False
        price = sale.price * self.economy.config.buy_back
        heavy = self.player.load + sale.item.weight > self.player.carry_limit + 1e-9
        if price > self.player.money + 1e-9 or heavy:
            return False
        self.economy.pay(PLAYER, OUTSIDE, price, Kind.PURCHASE, buyer.place)
        sales = list(self.player.sales)
        sales.remove(sale)
        self.player.sales = sales
        self.player.items = [*self.player.items, sale.item]
        logger.info("%s  The player buys back %s from %s", self.clock, sale.item.name, buyer.name)
        return True

    def _kept(self, place: Id) -> list[Sale]:
        return sorted((s for s in self.player.sales if s.place == place), key=lambda s: s.price)


def counted(items: list[Item]) -> str:
    """Each kind once, with how many: "Copper wire ×2, Circuit board"."""
    counts = Counter(item.name for item in items)
    return ", ".join(name if n == 1 else f"{name} ×{n}" for name, n in counts.items())
