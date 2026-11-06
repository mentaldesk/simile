import logging
from collections.abc import Callable
from itertools import count
from typing import TYPE_CHECKING

from simile.player.config import DEFAULT_CONFIG, PlayerConfig
from simile.player.health import DEFAULT_HEALTH, HealthConfig
from simile.player.where import here
from simile.protocol import Vital
from simile.schema import PLAYER_ID, Body, Corpse, Id, ItemKind, MapTile, Player
from simile.sim import Clock
from simile.world.movement import Movement, Point, cell_of
from simile.world.paths import Spot

if TYPE_CHECKING:
    from simile.economy.economy import Economy

logger = logging.getLogger(__name__)


class Death:
    """The player's death, whatever ran out: a corpse stays where they fell, and they wake in their
    bed in a new body."""

    def __init__(
        self,
        player: Player,
        movement: Movement,
        clock: Clock,
        *,
        economy: "Economy | None" = None,
        bed: Callable[[], Spot | None] = lambda: None,
        woke: Callable[[MapTile, Vital], None] = lambda home, cause: None,
        config: PlayerConfig = DEFAULT_CONFIG,
        health: HealthConfig = DEFAULT_HEALTH,
    ) -> None:
        self.player = player
        self.movement = movement
        self.clock = clock
        self.economy = economy
        """Its `player` is this one, so the money on the corpse goes through its ledger."""
        self.bed = bed
        self.woke = woke
        """Told where they wake, and what ran out."""
        self.config = config
        self.health = health

    def die(self, cause: Vital) -> None:
        """Leaves their money, all but the lamp and every bionic on a corpse where they are, or in
        their bed if the server doesn't know where that is, and wakes them with no effects in a
        whole organic body. What they know, stash, sold and repaired stays theirs."""
        player = self.player
        home = self._waking()
        fell = here(self.movement) or Point(home.x, home.y, home.map)
        corpse = Corpse(
            id=next_corpse(player.corpses),
            owner=PLAYER_ID,
            at=ground(self.movement, fell),
            money=player.money,
            items=[item for item in player.items if item.kind is not ItemKind.LAMP],
            bionics=player.body.bionics,
        )
        player.corpses = [*player.corpses, corpse]
        player.items = [item for item in player.items if item.kind is ItemKind.LAMP]
        if self.economy is not None:
            self.economy.drop(player.money)
        player.money = 0.0
        player.body = Body()
        player.effects = []
        player.health = self.health.waking
        player.power = 1.0
        player.hunger = min(player.hunger, self.config.waking)
        self.movement.track(PLAYER_ID, Point(home.x, home.y, home.map))
        logger.info("%s  The player dies (%s) and wakes at home", self.clock, cause)
        self.woke(home, cause)

    def _waking(self) -> MapTile:
        """Their bed at home, or its entry without one."""
        bed = self.bed()
        if bed is not None:
            return MapTile(map=bed.map, x=bed.x, y=bed.y)
        house = self.movement.town.location(self.config.home)
        return MapTile(map=house.map, x=house.entry.x, y=house.entry.y)


def next_corpse(corpses: list[Corpse]) -> Id:
    """An id none of `corpses` has, which a reload can't reuse since they're saved with it."""
    taken = {corpse.id for corpse in corpses}
    return next(id for n in count(len(corpses) + 1) if (id := f"corpse_{n}") not in taken)


def ground(movement: Movement, here: Point) -> MapTile:
    """The cell they're on, or the first one below it to stand on."""
    x, y = (max(n, 0) for n in cell_of(here))
    town = movement.maps.get(here.map)
    if town is not None:
        x, y = min(x, town.width - 1), min(y, town.height - 1)
        y = next((row for row in range(y, town.height) if town.standing(x, row)), y)
    return MapTile(map=here.map, x=x, y=y)
