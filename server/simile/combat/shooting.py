"""Firing and reloading: README.md."""

import logging

from simile.creatures.engine import Creature, Creatures
from simile.schema import PLAYER_ID, Item, ItemKind, Material, Player, SideFacing
from simile.sim import Clock
from simile.world.movement import Movement, Point, cell_of

logger = logging.getLogger(__name__)

RANGE = 12
"""Columns a shot carries past the one the player stands in."""
DAMAGE = {Material.PLASTIC: 1}
"""Points of a creature's `health` a round from a weapon of each material takes."""
LASTS = {Material.PLASTIC: 30}
"""Rounds a new weapon of each material fires before it's worn out."""


def _usable(item: Item) -> bool:
    return item.kind is ItemKind.WEAPON and bool(item.condition)


def _room(weapon: Item) -> int:
    return (weapon.capacity or 0) - (weapon.rounds or 0)


def _worn(weapon: Item) -> float:
    """Its condition after one more round, counted in rounds so the last leaves exactly none."""
    lasts = LASTS[weapon.material or Material.PLASTIC]
    return max(round((weapon.condition or 0) * lasts) - 1, 0) / lasts


class Shooting:
    """The player's `fire` and `reload`."""

    def __init__(
        self, player: Player, movement: Movement, creatures: Creatures, clock: Clock | None = None
    ) -> None:
        self.player = player
        self.movement = movement
        self.creatures = creatures
        self.clock = clock

    def fire(self, facing: SideFacing) -> bool:
        """Whether it fired, from the first weapon that's loaded and not worn out."""
        weapon = next((i for i in self.player.items if _usable(i) and i.rounds), None)
        here = self.movement.entities().get(PLAYER_ID)
        if weapon is None or here is None:
            return False
        fired = {"rounds": (weapon.rounds or 0) - 1, "condition": _worn(weapon)}
        self.player.items = [
            item.model_copy(update=fired) if item is weapon else item for item in self.player.items
        ]
        target = self._target(here, 1 if facing is SideFacing.EAST else -1)
        if target is not None:
            logger.info("%s  The player shoots a %s", self.clock or "", target.kind.id)
            self.creatures.hurt(target, DAMAGE[weapon.material or Material.PLASTIC])
        return True

    def reload(self) -> bool:
        """Whether any rounds went in, to the first weapon with room that's not worn out."""
        weapon = next((i for i in self.player.items if _usable(i) and _room(i) > 0), None)
        if weapon is None:
            return False
        room = _room(weapon)
        kept: list[Item] = []
        for item in self.player.items:
            taken = 0
            if item.kind is ItemKind.ROUNDS and item.material == weapon.material:
                taken = min(room, int(item.amount))
            room -= taken
            if not taken:
                kept.append(item)
            elif taken < item.amount:
                kept.append(item.model_copy(update={"amount": item.amount - taken}))
        loaded = _room(weapon) - room
        if not loaded:
            return False
        full = {"rounds": (weapon.rounds or 0) + loaded}
        self.player.items = [
            item.model_copy(update=full) if item is weapon else item for item in kept
        ]
        return True

    def _target(self, here: Point, way: int) -> Creature | None:
        """The nearest creature in line, column by column until walls have stopped both rows."""
        town = self.creatures.maps.get(here.map)
        if town is None:
            return None
        x, feet = cell_of(here)
        rows = {feet, feet - 1}
        alive = [c for c in self.creatures.all.values() if c.map == here.map and c.down is None]
        for column in range(x, x + way * (RANGE + 1), way):
            rows = {row for row in rows if not town.solid(column, row)}
            if not rows:
                return None
            hit = [c for c in alive if c.cell[0] == column and c.cell[1] in rows]
            if hit:
                return min(hit, key=lambda c: abs(c.x - here.x))
        return None
