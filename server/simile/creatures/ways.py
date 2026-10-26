"""The ways a creature decides where to go. A kind lists them first first, and each tick the
first with somewhere to go decides; P13 to P15 give each kind its own, with their numbers."""

import math
from collections.abc import Callable
from dataclasses import dataclass
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


@dataclass(frozen=True)
class Senses:
    """What a creature knows of the world this tick. The player is there only while a client is
    in the game and they're on its map, where the server last kept them."""

    now: float
    town: TownMap
    player: Player | None = None
    at: Point | None = None

    @property
    def lamp(self) -> bool:
        """Their lamp is on."""
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
    """Where a way sends a creature and what it's doing on the way, `state`, at `pace` times its
    kind's speed. It's `still` once there, and `idle` while it can't get nearer. `attacks` hurts
    the player whenever they're in reach."""

    target: Cell
    state: CreatureState
    pace: float = 1.0
    attacks: bool = False
    still: CreatureState = CreatureState.IDLE


class Way(Protocol):
    def aim(self, creature: "Creature", senses: Senses) -> Aim | None: ...


type Condition = Callable[[Senses], bool]
type Lure = Callable[[Senses], tuple[float, float] | None]


def food(senses: Senses) -> Point | None:
    """The player, while they carry food."""
    return senses.at if senses.carries(ItemKind.FOOD) else None


def lamp(senses: Senses) -> tuple[float, float] | None:
    """The player's lamp, while it's on."""
    return senses.light


def lamp_on(senses: Senses) -> bool:
    return senses.lamp


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
    """After the player while it can see them within `sight` and `when` holds, attacking in
    reach, and on to where it saw them last for `memory` after it loses sight of them."""

    sight: float = 6.0
    pace: float = 1.0
    memory: float = 2.0
    when: Condition | None = None

    def aim(self, creature: "Creature", senses: Senses) -> Aim | None:
        if self.when is not None and not self.when(senses):
            creature.seen = None
            return None
        at = senses.at
        if at is not None and creature.sees((at.x, at.y - CHEST), self.sight):
            creature.seen = ((at.x, at.y), senses.now)
        if creature.seen is None:
            return None
        (x, y), when = creature.seen
        target = creature.grid.ground(x, y - CHEST if creature.kind.flies else y)
        if senses.now - when > self.memory or target is None:
            creature.seen = None
            return None
        return Aim(target, CreatureState.CHASING, self.pace, attacks=True)


@dataclass(frozen=True)
class FleeLight:
    """Away from the player's lamp within `radius` of it, and with `lit`, out of the map's lit
    stretches: to the nearest dark cell within `within`, or else as far from the lamp as it
    can."""

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
    """Towards `lure` while it's within `within`, attacking in reach if it `attacks`."""

    lure: Lure
    within: float = 8.0
    pace: float = 1.0
    attacks: bool = False

    def aim(self, creature: "Creature", senses: Senses) -> Aim | None:
        point = self.lure(senses)
        if point is None or math.dist(creature.position, point) > self.within:
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
