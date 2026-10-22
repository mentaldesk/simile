import logging
from typing import TYPE_CHECKING

from simile.player.where import here, location
from simile.protocol import Buyer
from simile.schema import Id, Player
from simile.sim import Clock
from simile.world.movement import Movement, inside

if TYPE_CHECKING:
    from simile.economy.economy import Economy

logger = logging.getLogger(__name__)


class Trade:
    """Selling to whoever buys where the player stands, at the economy's prices."""

    def __init__(
        self, player: Player, movement: Movement, economy: "Economy", clock: Clock
    ) -> None:
        self.player = player
        self.movement = movement
        self.economy = economy
        """Its `player` is this one, so sales go through its ledger."""
        self.clock = clock

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
            return Buyer(place=place, name=stall.name, prices=prices)
        return None

    def sell(self, item: Id | None) -> bool:
        """Sells one carried item by id, or with None everything the buyer here buys. Whether
        they sold anything."""
        buyer = self.buyer()
        if buyer is None:
            return False
        kept = list(self.player.items)
        sold = [thing for thing in kept if thing.id in buyer.prices and item in (None, thing.id)]
        if item is not None:
            sold = sold[:1]
        for thing in sold:
            if self.economy.sell(buyer.place, thing):
                kept.remove(thing)
        if len(kept) == len(self.player.items):
            return False
        self.player.items = kept
        logger.info(
            "%s  The player sells %s to %s",
            self.clock,
            ", ".join(thing.name for thing in sold),
            buyer.name,
        )
        return True
