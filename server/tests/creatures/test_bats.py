import math
from functools import cache

import pytest

from simile.creatures.engine import Creatures, Sight
from simile.creatures.kind import Kind
from simile.creatures.kinds import BAT
from simile.creatures.placing import populate, spawns
from simile.player.kick import Kick
from simile.schema import CreatureKind, CreatureState, Item, ItemKind, MapTile, Player, SideFacing
from simile.street.jump import JUMP, LEGS
from simile.street.plan import Spawn
from simile.street.sewers import CAVE, FLOORS, GAP, LEVELS, SEWERS
from simile.world.map import TownMap, load_maps
from simile.world.movement import Point

from .conftest import side_view

STEP = 0.1
THROTTLE = 0.2
CLIMB = 1.5
FALL = 10.0
WALK = JUMP.run / 2
ROOM = side_view(
    "############",
    "#..........#",
    "#..........#",
    "#..........#",
    "############",
)
"""A room three rows high, standing on row 3."""

type Leg = tuple[float, float, float]
"""Where the player goes next, and how fast."""


def lamp(on: bool) -> Item:
    return Item(id="lamp", kind=ItemKind.LAMP, name="Lamp", weight=1.0, charge=1.0, on=on)


class Roosting:
    """A bat roosting at (3, 1), and the player standing at (8, 3) with their lamp off."""

    def __init__(self) -> None:
        self.player = Player(items=[lamp(False)])
        self.at = Point(8, 3, ROOM.id)
        self.harmed: list[Kind] = []
        self.creatures = Creatures(
            {ROOM.id: ROOM}, sense=lambda: Sight(self.player, self.at), harm=self.harmed.append
        )
        self.bat = self.creatures.spawn(BAT, MapTile(map=ROOM.id, x=3, y=1))

    def light(self, on: bool) -> None:
        self.player.items = [lamp(on)]

    def run(self, seconds: float) -> None:
        for _ in range(round(seconds / STEP)):
            self.creatures.tick(STEP)


def test_a_bat_hangs_at_its_roost_in_the_dark_and_attacks_only_by_lamplight() -> None:
    roost = Roosting()
    roost.run(5)
    assert roost.bat.state is CreatureState.ROOSTING and roost.harmed == []

    roost.light(True)
    roost.run(3)
    assert roost.harmed and set(roost.harmed) == {BAT}

    roost.light(False)
    roost.run(1)
    roost.harmed.clear()
    roost.run(5)
    assert roost.harmed == []
    assert roost.bat.cell == (3, 1) and roost.bat.state is CreatureState.ROOSTING


def test_a_bat_stays_on_a_player_who_runs_by_lamplight_and_attacks_again_once_rested() -> None:
    roost = Roosting()
    roost.light(True)
    for _ in range(50):
        if not roost.harmed:
            roost.run(STEP)
    for x in (4, 1, 10):
        roost.at = Point(x, 3, ROOM.id)
        roost.run(BAT.rest + 0.5)
    assert len(roost.harmed) >= 3


def test_a_kick_never_lands_on_a_bat_however_low_it_flies() -> None:
    roost = Roosting()
    roost.light(True)
    for _ in range(50):
        if roost.bat.state is not CreatureState.ATTACKING:
            roost.run(STEP)
    facing = SideFacing.WEST if roost.bat.x < roost.at.x else SideFacing.EAST
    kick = Kick(roost.at, facing, strength=4)
    assert roost.creatures.kickable(kick) is None
    roost.bat.y = 3.0
    assert roost.creatures.kickable(kick) is None


@cache
def maps(level: int) -> dict[str, TownMap]:
    return load_maps(level=level)


def bats(level: int, cave: bool) -> list[tuple[str, Spawn]]:
    return [
        (map_id, spawn)
        for map_id, spawn in spawns(level=level)
        if spawn.kind is CreatureKind.BAT and ("cave" in spawn.id) == cave
    ]


def harm(level: int, legs: list[Leg], lit: bool, cave: bool) -> float:
    """The health the zone's or the cave's bats take from the player along `legs`, from the
    first, with their lamp on if `lit`."""
    town = maps(level)[SEWERS]
    player = Player(items=[lamp(lit)])
    x, y, _ = legs[0]
    heard = Point(x, y, SEWERS)
    taken: list[Kind] = []
    creatures = Creatures({SEWERS: town}, sense=lambda: Sight(player, heard), harm=taken.append)
    populate(creatures, bats(level, cave))
    now = said = 0.0
    for tx, ty, pace in legs[1:]:
        while (x, y) != (tx, ty):
            now += STEP
            gap = math.dist((x, y), (tx, ty))
            share = min(1.0, pace * STEP / gap)
            x, y = (x + (tx - x) * share, y + (ty - y) * share) if share < 1 else (tx, ty)
            if now - said >= THROTTLE - 1e-9:
                heard, said = Point(x, y, SEWERS), now
            creatures.tick(STEP)
    for _ in range(round(1 / STEP)):
        creatures.tick(STEP)
    return sum(kind.damage for kind in taken)


def across_the_cave(town: TownMap, pace: float) -> list[Leg]:
    """In from the den, up through the cave's three tiers and over the gap to its stash, then
    down into the gap and back out."""
    [light] = [light for light in town.light if light.id == "sewers_cave"]
    west, east = light.area.x + 1, light.area.x + CAVE
    there = [
        (west - 1, FLOORS[0], pace),
        (east - GAP - 3, FLOORS[0], pace),
        (east - GAP - 3, FLOORS[1], CLIMB),
        (west + 1, FLOORS[1], pace),
        (west + 1, FLOORS[2], CLIMB),
        (east - GAP - 2, FLOORS[2], pace),
        (east, FLOORS[2], pace),
    ]
    back = [(east - 2, FLOORS[2], pace), (east - 2, FLOORS[0], FALL), (west - 1, FLOORS[0], pace)]
    return [*there, *back]


def across_the_roosts(level: int, pace: float) -> list[list[Leg]]:
    """Along the floor of each room in zone 0 where bats roost, and back."""
    areas = {(a.x, a.y + 3, a.width) for _, spawn in bats(level, cave=False) if (a := spawn.area)}
    return [
        [(x, floor, pace), (x + width - 1, floor, pace), (x, floor, pace)]
        for x, floor, width in areas
    ]


PACES = (WALK, JUMP.run, *(jump.run for jump in LEGS.values()))


@pytest.mark.parametrize("level", range(LEVELS))
def test_the_cave_crosses_with_the_lamp_off_but_not_by_lamplight_on_any_legs(level: int) -> None:
    town = maps(level)[SEWERS]
    for pace in PACES:
        assert harm(level, across_the_cave(town, pace), lit=False, cave=True) == 0
        assert harm(level, across_the_cave(town, pace), lit=True, cave=True) >= 1, pace


@pytest.mark.parametrize("level", range(LEVELS))
def test_zone_0_s_bats_cost_some_health_by_lamplight_and_none_in_the_dark(level: int) -> None:
    for legs in across_the_roosts(level, WALK):
        assert harm(level, legs, lit=False, cave=False) == 0
        assert 0 < harm(level, legs, lit=True, cave=False) < 0.4
