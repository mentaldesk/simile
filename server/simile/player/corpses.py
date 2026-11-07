import logging
import math
from collections.abc import Callable, Iterable, Mapping
from itertools import count
from typing import TYPE_CHECKING, Final

from simile.player.config import DEFAULT_CONFIG, PlayerConfig
from simile.player.health import DEFAULT_HEALTH, HealthConfig
from simile.player.pickups import Claim, joined
from simile.player.where import here
from simile.protocol import Vital
from simile.schema import (
    PLAYER_ID,
    Bionic,
    Body,
    Corpse,
    Id,
    Item,
    ItemKind,
    MapTile,
    Player,
    Recipe,
)
from simile.sim import Clock
from simile.world.movement import Movement, Point, cell_of
from simile.world.paths import Spot

if TYPE_CHECKING:
    from simile.economy.economy import Economy

logger = logging.getLogger(__name__)

BIONIC_WEIGHTS: Final[dict[Bionic, float]] = {
    Bionic.DATAJACK: 0.5,
    Bionic.INFRARED_EYE: 0.5,
    Bionic.POWER_CELL: 2.0,
    Bionic.POWER_CELL_2: 3.0,
    Bionic.POWER_CELL_3: 4.0,
    Bionic.BIONIC_LEGS: 6.0,
    Bionic.BIONIC_LEGS_2: 7.0,
    Bionic.BIONIC_LEGS_3: 8.0,
    Bionic.SPRING_FEET: 2.0,
    Bionic.SPRING_FEET_2: 3.0,
}
"""What each bionic weighs in kg once it's out of the body, against their carry limit."""


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
        """Leaves their money, all but the lamp and every bionic on a corpse where they are, or
        where they wake if the server doesn't know where that is, and wakes them with no effects
        in a whole organic body. What they know, stash, sold and repaired stays theirs."""
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


class Salvage:
    """E at their own corpse, one more claim on `pick_up`: its money, then each of its items and
    bionics that fits under their carry limit. What doesn't fit stays on it."""

    def __init__(
        self,
        player: Player,
        economy: "Economy",
        clock: Clock,
        recipes: Mapping[Bionic, Recipe],
        config: PlayerConfig = DEFAULT_CONFIG,
    ) -> None:
        self.player = player
        self.economy = economy
        """Its `player` is this one, so the money comes back through its ledger."""
        self.clock = clock
        self.recipes = recipes
        """What each bionic is called."""
        self.config = config

    def claim(self, at: Point) -> Claim | None:
        """The nearest corpse in reach that they can take something from, the oldest on a tie."""
        near = [
            (distance, corpse)
            for corpse in self.player.corpses
            if corpse.at.map == at.map
            and self._gives(corpse)
            and (distance := math.dist(at, (corpse.at.x, corpse.at.y))) <= self.config.reach
        ]
        if not near:
            return None
        distance, corpse = min(near, key=lambda found: found[0])
        return Claim(distance, lambda: self.take(corpse))

    def take(self, corpse: Corpse) -> None:
        """Leaves the corpse in its place with what didn't fit, however little that is."""
        room = self._room()
        items, kept_items, room = _fitting(corpse.items, room)
        bionics, kept, _ = _fitting(map(self.item, corpse.bionics), room)
        rest = corpse.model_copy(
            update={
                "money": 0.0,
                "items": kept_items,
                "bionics": [item.bionic for item in kept if item.bionic],
            }
        )
        self.player.corpses = [rest if c.id == corpse.id else c for c in self.player.corpses]
        self.player.items = joined(self.player.items, [*items, *bionics])
        if corpse.money:
            self.economy.recover(corpse.money)
        logger.info("%s  The player salvages %s", self.clock, corpse.id)

    def item(self, bionic: Bionic) -> Item:
        """`bionic` as a part they carry, to have refitted."""
        return Item(
            id=bionic.value,
            kind=ItemKind.BIONIC,
            name=self.recipes[bionic].name,
            weight=BIONIC_WEIGHTS[bionic],
            bionic=bionic,
        )

    def _room(self) -> float:
        return self.player.carry_limit - self.player.load

    def _gives(self, corpse: Corpse) -> bool:
        things = [*corpse.items, *map(self.item, corpse.bionics)]
        return bool(corpse.money) or any(thing.load <= self._room() + 1e-9 for thing in things)


def _fitting(items: Iterable[Item], room: float) -> tuple[list[Item], list[Item], float]:
    """Of `items`, in order, those that fit in `room`, those that don't, and the room left."""
    taken: list[Item] = []
    kept: list[Item] = []
    for item in items:
        if item.load <= room + 1e-9:
            taken.append(item)
            room -= item.load
        else:
            kept.append(item)
    return taken, kept, room


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
