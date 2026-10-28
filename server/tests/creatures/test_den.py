import math
from datetime import UTC, datetime
from functools import cache

import pytest

from simile.creatures.engine import Creatures, Sight
from simile.creatures.kind import Kind
from simile.creatures.placing import populate, spawns
from simile.player.health import Health
from simile.schema import PLAYER_ID, Bionic, CreatureKind, Player
from simile.sim import Clock, EventBus
from simile.street.jump import JUMP, LEGS, Jump
from simile.street.sewers import DEN, FLOORS, LEVELS, SEWERS
from simile.world import Movement, Point
from simile.world.map import TownMap, load_maps

STEP = 0.1
THROTTLE = 0.2
"""Real seconds between the client's `player_move`s, as the server hears where they are."""
CLIMB = 1.5
FALL = 10.0
"""Tiles a second up a ladder, as the client climbs, and down a drop, about as it falls."""
FLOOR, LOFT = FLOORS[0], FLOORS[1]


@cache
def maps(level: int) -> dict[str, TownMap]:
    return load_maps(level=level)


def route(town: TownMap, run: float) -> list[tuple[float, float, float, float]]:
    """In through the den's door, across the dogs' floor and up its far ladder to the loft, down
    the hole by that ladder and back out: each point, the pace there and how long they stop."""
    [door] = [light.area.x for light in town.light if light.id == "sewers_den"]
    ladder, outside = door + DEN - 1, door - 3
    return [
        (outside, FLOOR, run, 0.0),
        (ladder, FLOOR, run, 0.0),
        (ladder, LOFT, CLIMB, 0.0),
        (door + 5, LOFT, run, 1.0),
        (ladder + 1, LOFT, run, 0.0),
        (ladder + 1, FLOOR, FALL, 0.0),
        (outside, FLOOR, run, 0.0),
    ]


def through(level: int, jump: Jump) -> Player:
    """The player through the den and back from full health: their health as they come out, or
    after they collapse."""
    town = maps(level)[SEWERS]
    player = Player()
    movement = Movement(maps(level), EventBus())
    collapsed = []
    health = Health(player, movement, Clock(datetime(2026, 1, 1, tzinfo=UTC)))
    health.collapse = lambda: collapsed.append(True)
    points = route(town, jump.run)
    x, y = points[0][:2]
    heard = Point(x, y, SEWERS)

    def harm(kind: Kind) -> None:
        health.hurt(kind.damage)

    creatures = Creatures({SEWERS: town}, sense=lambda: Sight(player, heard), harm=harm)
    dogs = [(m, s) for m, s in spawns(level=level) if s.kind is CreatureKind.DOG]
    populate(creatures, dogs)
    now, said = 0.0, 0.0
    for tx, ty, pace, stop in points[1:]:
        while (x, y) != (tx, ty) or stop > 0:
            if collapsed:
                player.health = 0.0
                return player
            now += STEP
            if (x, y) == (tx, ty):
                stop -= STEP
            else:
                gap = math.dist((x, y), (tx, ty))
                share = min(1.0, pace * STEP / gap)
                x, y = (x + (tx - x) * share, y + (ty - y) * share) if share < 1 else (tx, ty)
            if now - said >= THROTTLE - 1e-9:
                heard, said = Point(x, y, SEWERS), now
                movement.track(PLAYER_ID, heard)
            creatures.tick(STEP)
    return player


@pytest.mark.parametrize("level", range(LEVELS))
def test_a_player_on_their_own_legs_collapses_in_the_den(level: int) -> None:
    assert through(level, JUMP).health == 0


@pytest.mark.parametrize("level", range(LEVELS))
def test_the_first_bionic_legs_get_through_with_little_health_left(level: int) -> None:
    assert 0 < through(level, LEGS[Bionic.BIONIC_LEGS]).health < 0.3


@pytest.mark.parametrize("level", range(LEVELS))
def test_the_best_legs_get_through_hurt(level: int) -> None:
    assert 0 < through(level, LEGS[Bionic.BIONIC_LEGS_3]).health < 0.8
