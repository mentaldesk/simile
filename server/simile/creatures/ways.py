"""How a creature decides where to go: README.md's *Moving*."""

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, NamedTuple, Protocol

from simile.creatures.grid import Cell
from simile.schema import CreatureState, ItemKind, Player
from simile.world.map import TownMap
from simile.world.movement import Point

if TYPE_CHECKING:
    from simile.creatures.engine import Creature

LAMP = 4.5
"""Tiles the player's lamp lights around them, as the client draws it (`LAMP_RADIUS`)."""
CHEST = 1.0
"""Tiles above the player's feet that a creature looks at and their lamp shines from."""
ON_FLOOR = (0.9, 2.5)
"""Tiles below and above a creature's floor the player's feet are still on it: as high as a jump
off it, but not a ledge three rows up or a floor over its ceiling."""


@dataclass(frozen=True)
class Senses:
    """The player is here only while a client is in the game and they're on the creature's map."""

    now: float
    town: TownMap
    player: Player | None = None
    at: Point | None = None
    salvage: Mapping[Cell, str] = field(default_factory=dict)
    """The salvage lying on the map, by its pickup's cell, while the player's on it."""

    @property
    def lamp(self) -> bool:
        return (
            self.at is not None
            and self.player is not None
            and any(item.kind is ItemKind.LAMP and item.on for item in self.player.items)
        )

    def carries(self, kind: ItemKind) -> bool:
        return (
            self.at is not None
            and self.player is not None
            and any(item.kind is kind for item in self.player.items)
        )

    @property
    def light(self) -> tuple[float, float] | None:
        """Where their lamp shines from, while it's on."""
        return (self.at.x, self.at.y - CHEST) if self.at is not None and self.lamp else None


class Aim(NamedTuple):
    """Where a way sends a creature, and its state there: `still` once there, `idle` if stuck."""

    target: Cell
    state: CreatureState
    pace: float = 1.0
    attacks: bool = False
    still: CreatureState = CreatureState.IDLE
    collects: bool = False


class Way(Protocol):
    def aim(self, creature: "Creature", senses: Senses) -> Aim | None: ...


type Condition = Callable[[Senses], bool]
type Lure = Callable[[Senses], tuple[float, float] | None]


def food(senses: Senses) -> Point | None:
    return senses.at if senses.carries(ItemKind.FOOD) else None


def lamp(senses: Senses) -> tuple[float, float] | None:
    return senses.light


def lamp_on(senses: Senses) -> bool:
    return senses.lamp


def fitted(senses: Senses) -> bool:
    """While the player has any bionic."""
    return senses.player is not None and bool(senses.player.body.bionics)


@dataclass(frozen=True)
class Patrol:
    """Back and forth along its route, stopping `pause` at each end."""

    pause: float = 1.5

    def aim(self, creature: "Creature", senses: Senses) -> Aim | None:
        route = creature.route
        if not route:
            return None
        target = route[creature.leg % len(route)]
        if creature.resting and creature.cell == target:
            if creature.paused is None:
                creature.paused = senses.now + self.pause
            if senses.now >= creature.paused:
                creature.leg += 1
                creature.paused = None
                target = route[creature.leg % len(route)]
        return Aim(target, CreatureState.MOVING)


@dataclass(frozen=True)
class Chase:
    """After the player while it sees them, then where it saw them last for `memory`. One that
    keeps to its `floor` sees them only on it (`ON_FLOOR`), with floor it walks all the way
    between them."""

    sight: float = 6.0
    pace: float = 1.0
    memory: float = 2.0
    when: Condition | None = None
    floor: bool = False

    def aim(self, creature: "Creature", senses: Senses) -> Aim | None:
        if self.when is not None and not self.when(senses):
            creature.seen = None
            return None
        at = senses.at
        on = at is not None and (not self.floor or _on_floor(creature, at))
        if at is not None and on and creature.sees((at.x, at.y - CHEST), self.sight):
            creature.seen = ((at.x, at.y), senses.now)
        if creature.seen is None:
            return None
        (x, y), when = creature.seen
        target = creature.grid.ground(x, y - CHEST if creature.kind.flies else y)
        if senses.now - when > self.memory or target is None:
            creature.seen = None
            return None
        return Aim(target, CreatureState.CHASING, self.pace, attacks=True)


def _on_floor(creature: "Creature", at: Point) -> bool:
    """Whether the player's feet at `at` are on the floor the creature walks to them along, and
    not on a ladder or stairs it doesn't take."""
    below, above = ON_FLOOR
    if not -above <= at.y - creature.y <= below:
        return False
    grid = creature.grid
    feet = (math.floor(at.x + 0.5), math.ceil(round(at.y, 6)))
    if grid.town.climb(*feet) is not None and not grid.takes(feet):
        return False
    x, row = creature.cell
    there = math.floor(at.x + 0.5)
    step = 1 if there >= x else -1
    return all(grid.allowed((cx, row)) for cx in range(x, there + step, step))


@dataclass(frozen=True)
class FleeLight:
    """To the nearest dark cell within `within`, or else as far from the lamp as it can."""

    radius: float = LAMP
    lit: bool = True
    within: float = 12.0
    pace: float = 1.0

    def aim(self, creature: "Creature", senses: Senses) -> Aim | None:
        light = senses.light

        def bright(cell: Cell) -> bool:
            if light is not None and math.dist(cell, light) <= self.radius:
                return True
            return self.lit and senses.town.lit(*cell)

        start = creature.cell
        if not bright(start):
            return None
        grid = creature.grid
        target = grid.nearest(
            start, lambda cell: None if bright(cell) else math.dist(cell, start), self.within
        )
        if target == start and light is not None:
            target = grid.nearest(start, lambda cell: -math.dist(cell, light), self.within)
        return Aim(target, CreatureState.FLEEING, self.pace)


@dataclass(frozen=True)
class DrawnTo:
    """Towards `lure` while it's within `within`, and on its `floor` if it keeps to it (as
    `Chase`), attacking in reach if it `attacks`."""

    lure: Lure
    within: float = 8.0
    pace: float = 1.0
    attacks: bool = False
    floor: bool = False

    def aim(self, creature: "Creature", senses: Senses) -> Aim | None:
        point = self.lure(senses)
        if point is None or math.dist(creature.position, point) > self.within:
            return None
        if self.floor and not _on_floor(creature, Point(*point, creature.map)):
            return None
        target = creature.grid.ground(*point)
        if target is None:
            return None
        state = CreatureState.CHASING if self.attacks else CreatureState.MOVING
        return Aim(target, state, self.pace, self.attacks)


@dataclass(frozen=True)
class Roost:
    """A bat back to its roost to hang there, while `when` holds."""

    when: Condition | None = None

    def aim(self, creature: "Creature", senses: Senses) -> Aim | None:
        if creature.roost is None or (self.when is not None and not self.when(senses)):
            return None
        return Aim(creature.roost, CreatureState.MOVING, still=CreatureState.ROOSTING)


@dataclass(frozen=True)
class Scurry:
    """Home after an attack, until it's rested."""

    pace: float = 1.5

    def aim(self, creature: "Creature", senses: Senses) -> Aim | None:
        if senses.now >= creature.rested:
            return None
        return Aim(creature.home, CreatureState.FLEEING, self.pace)


@dataclass(frozen=True)
class Collect:
    """To the nearest salvage lying within `within`, to take it."""

    within: float = 4.0
    pace: float = 1.0

    def aim(self, creature: "Creature", senses: Senses) -> Aim | None:
        salvage = senses.salvage
        if not salvage:
            return None
        target = creature.grid.nearest(
            creature.cell, lambda cell: 0.0 if cell in salvage else None, self.within
        )
        if target not in salvage:
            return None
        return Aim(target, CreatureState.MOVING, self.pace, collects=True)
