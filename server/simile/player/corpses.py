import logging
import math
from collections.abc import Callable, Mapping
from itertools import count
from typing import TYPE_CHECKING, Final

from simile.player.config import DEFAULT_CONFIG, PlayerConfig
from simile.player.health import DEFAULT_HEALTH, HealthConfig
from simile.player.pickups import joined
from simile.player.stash import fitting, split
from simile.player.where import here
from simile.protocol import TakeMessage, Vital
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
    """The player's death, whatever ran out: a corpse lies where they fell, if anything's on it,
    and they wake in their bed in a new body."""

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
        where they wake if the server doesn't know where that is, or no corpse with none of those,
        and wakes them with no effects in a whole organic body. What they know, stash, sold and
        repaired stays theirs."""
        player = self.player
        home = self._waking()
        fell = here(self.movement) or Point(home.x, home.y, home.map)
        items = [item for item in player.items if item.kind is not ItemKind.LAMP]
        if player.money or items or player.body.bionics:
            corpse = Corpse(
                id=next_corpse(player),
                owner=PLAYER_ID,
                at=ground(self.movement, fell),
                money=player.money,
                items=items,
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
    """Taking things one at a time from their own corpses and the piles they left: money, an item
    or a bionic. A corpse or pile with nothing left goes."""

    def __init__(
        self,
        player: Player,
        movement: Movement,
        economy: "Economy",
        clock: Clock,
        recipes: Mapping[Bionic, Recipe],
        config: PlayerConfig = DEFAULT_CONFIG,
    ) -> None:
        self.player = player
        self.movement = movement
        self.economy = economy
        """Its `player` is this one, so the money comes back through its ledger."""
        self.clock = clock
        self.recipes = recipes
        """What each bionic is called."""
        self.config = config

    def take(self, message: TakeMessage) -> bool:
        """Takes the thing `message` names, or as much of a stack as fits. Whether any moved."""
        if message.corpse is not None:
            return self._from_corpse(message.corpse, message.item, message.bionic)
        return message.pile is not None and self._from_pile(message.pile, message.item)

    def bionics(self) -> list[Item]:
        """What each kind of bionic on their corpses comes out as, once each."""
        lying = (bionic for corpse in self.player.corpses for bionic in corpse.bionics)
        return [self.item(bionic) for bionic in dict.fromkeys(lying)]

    def item(self, bionic: Bionic) -> Item:
        """`bionic` as a part they carry, to have refitted."""
        recipe = self.recipes.get(bionic)
        return Item(
            id=bionic.value,
            kind=ItemKind.BIONIC,
            name=recipe.name if recipe else bionic.value.replace("_", " ").capitalize(),
            weight=BIONIC_WEIGHTS[bionic],
            bionic=bionic,
        )

    def _from_corpse(self, id: Id, item: Id | None, bionic: Bionic | None) -> bool:
        corpse = next((corpse for corpse in self.player.corpses if corpse.id == id), None)
        if corpse is None or not self._reaches(corpse.at):
            return False
        if bionic is not None:
            if bionic not in corpse.bionics or fitting(self.item(bionic), self._room()) <= 0:
                return False
            bionics = list(corpse.bionics)
            bionics.remove(bionic)
            self._carry(self.item(bionic))
            self._leave(corpse.model_copy(update={"bionics": bionics}))
        elif item is not None:
            taken = split(corpse.items, item, self._room())
            if taken is None:
                return False
            self._carry(taken[0])
            self._leave(corpse.model_copy(update={"items": taken[1]}))
        else:
            if not corpse.money:
                return False
            self._leave(corpse.model_copy(update={"money": 0.0}))
            self.economy.recover(corpse.money)
        logger.info("%s  The player salvages from %s", self.clock, id)
        return True

    def _leave(self, rest: Corpse) -> None:
        corpses = (rest if corpse.id == rest.id else corpse for corpse in self.player.corpses)
        self.player.corpses = [c for c in corpses if c.money or c.items or c.bionics]

    def _from_pile(self, at: MapTile, item: Id | None) -> bool:
        if not self._reaches(at):
            return False
        left = self.player.left
        for index, pile in enumerate(left):
            if pile.at != at:
                continue
            if item is None and pile.money:
                rest = pile.model_copy(update={"money": 0.0})
                self.economy.recover(pile.money)
            elif item is not None and (taken := split(pile.items, item, self._room())):
                rest = pile.model_copy(update={"items": taken[1]})
                self._carry(taken[0])
            else:
                continue
            kept = [rest] if rest.items or rest.money else []
            self.player.left = [*left[:index], *kept, *left[index + 1 :]]
            return True
        return False

    def _carry(self, item: Item) -> None:
        self.player.items = joined(self.player.items, [item])

    def _room(self) -> float:
        return self.player.carry_limit - self.player.load

    def _reaches(self, tile: MapTile) -> bool:
        at = here(self.movement)
        return (
            at is not None
            and at.map == tile.map
            and math.dist(at, (tile.x, tile.y)) <= self.config.reach
        )


def next_corpse(player: Player) -> Id:
    """Counts a new body and gives its id, which no corpse has had, even one that's gone."""
    lying = {corpse.id for corpse in player.corpses}
    player.bodies = next(n for n in count(player.bodies + 1) if f"corpse_{n}" not in lying)
    return f"corpse_{player.bodies}"


def ground(movement: Movement, here: Point) -> MapTile:
    """The cell they're on, or the first one below it to stand on."""
    x, y = (max(n, 0) for n in cell_of(here))
    town = movement.maps.get(here.map)
    if town is not None:
        x, y = min(x, town.width - 1), min(y, town.height - 1)
        y = next((row for row in range(y, town.height) if town.standing(x, row)), y)
    return MapTile(map=here.map, x=x, y=y)
