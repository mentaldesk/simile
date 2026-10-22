import logging
import math
from datetime import timedelta
from typing import TYPE_CHECKING, NamedTuple

from simile.player.config import DEFAULT_CONFIG, PlayerConfig
from simile.player.where import here
from simile.schema import Id, Item, MapTile, Pile, Player
from simile.sim import Clock
from simile.world.map import Pickup, PickupKind
from simile.world.movement import Movement

if TYPE_CHECKING:
    from simile.economy.economy import Economy

logger = logging.getLogger(__name__)


class Found(NamedTuple):
    """A pile in reach: one of what they left, by `index`, or what lies at a `pickup`."""

    pile: Pile
    index: int = -1
    pickup: Id | None = None


class Pickups:
    """What lies in the world for the player to pick up, and picking it up: what they left, the
    maps' secrets until they take them, and their salvage, which comes back a while after."""

    def __init__(
        self,
        player: Player,
        movement: Movement,
        economy: "Economy",
        clock: Clock,
        config: PlayerConfig = DEFAULT_CONFIG,
    ) -> None:
        self.player = player
        self.movement = movement
        self.economy = economy
        """Its `player` is this one, so money they pick up goes through its ledger."""
        self.clock = clock
        self.config = config
        self.lying: dict[Id, Pile] = {}
        """What lies at each of the maps' pickups until it's taken, by pickup id."""
        self.respawn: dict[Id, timedelta] = {}
        """How long after it's taken each salvage pickup has another lying there."""
        for town in movement.maps.values():
            for pickup in town.pickups:
                if (pile := self._pile(pickup)) is not None:
                    self.lying[pickup.id] = pile

    def piles(self) -> list[Pile]:
        """What lies at the pickups now."""
        return [pile for pickup, pile in self.lying.items() if self._there(pickup)]

    def pick_up(self) -> bool:
        """Takes the money and what still fits from the nearest pile in reach. Whether they took
        anything."""
        found = self._nearest()
        if found is None:
            return False
        room = self.player.carry_limit - self.player.load
        taken: list[Item] = []
        kept: list[Item] = []
        for item in found.pile.items:
            if item.weight <= room + 1e-9:
                taken.append(item)
                room -= item.weight
            else:
                kept.append(item)
        if not taken and not found.pile.money:
            return False
        if found.pile.money:
            self.economy.find(found.pile.money, found.pickup)
        rest = [Pile(at=found.pile.at, items=kept)] if kept else []
        left = self.player.left
        if found.pickup is None:
            self.player.left = [*left[: found.index], *rest, *left[found.index + 1 :]]
        else:
            self.player.taken = {**self.player.taken, found.pickup: self.clock.now}
            self.player.left = [*left, *rest]
        self.player.items = [*self.player.items, *taken]
        return True

    def _there(self, pickup: Id) -> bool:
        """Whether it's never been taken, or it's salvage and long enough ago."""
        taken = self.player.taken.get(pickup)
        if taken is None:
            return True
        respawn = self.respawn.get(pickup)
        return respawn is not None and self.clock.now - taken >= respawn

    def _nearest(self) -> Found | None:
        at = here(self.movement)
        if at is None:
            return None
        piles = [Found(pile, index=index) for index, pile in enumerate(self.player.left)]
        piles += [
            Found(pile, pickup=pickup) for pickup, pile in self.lying.items() if self._there(pickup)
        ]
        near = [
            (distance, order)
            for order, found in enumerate(piles)
            if found.pile.at.map == at.map
            and (distance := math.dist(at, (found.pile.at.x, found.pile.at.y))) <= self.config.reach
        ]
        return piles[min(near)[1]] if near else None

    def _pile(self, pickup: Pickup) -> Pile | None:
        at = MapTile(map=pickup.map, x=pickup.x, y=pickup.y)
        if pickup.kind is PickupKind.SALVAGE:
            salvage = self.config.salvage.get(pickup.id)
            if salvage is None:
                logger.warning("Nothing is set to lie at the salvage pickup %s", pickup.id)
                return None
            self.respawn[pickup.id] = timedelta(hours=salvage.respawn)
            return Pile(at=at, items=[salvage.item])
        items = [] if pickup.item is None else [pickup.item]
        if not items and not pickup.money:
            logger.warning("The secret %s holds nothing", pickup.id)
            return None
        return Pile(at=at, items=items, money=pickup.money)
