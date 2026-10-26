import math

import pytest

from simile.creatures.engine import COLLECTING, Creature, Creatures, Sight
from simile.creatures.kind import Kind
from simile.creatures.kinds import BOT, DOG, RAT
from simile.player.kick import Kick
from simile.schema import (
    Bionic,
    Body,
    CreatureState,
    Item,
    ItemKind,
    MapTile,
    Player,
    SideFacing,
)
from simile.street.jump import LEGS
from simile.world.map import TownMap
from simile.world.movement import Point

from .conftest import LOWER, TWO_FLOORS, UPPER, side_view

STEP = 0.1
ROW = side_view(
    "######################",
    "#....................#",
    "#....................#",
    "######################",
)
"""One long floor, standing row 2."""
RATION = Item(id="ration_pack", kind=ItemKind.FOOD, name="Ration pack", weight=0.5)
FITTED = Body(vertebra=Bionic.DATAJACK)


class World:
    def __init__(self, salvage: dict[tuple[int, int], str] | None = None) -> None:
        self.player = Player()
        self.at: Point | None = None
        self.harmed: list[Kind] = []
        self.collected: list[str] = []
        self.lying = dict(salvage or {})

        def collect(pickup: str) -> None:
            self.collected.append(pickup)
            self.lying = {cell: id for cell, id in self.lying.items() if id != pickup}

        self.creatures = Creatures(
            {ROW.id: ROW},
            sense=lambda: Sight(self.player, self.at),
            harm=self.harmed.append,
            salvage=lambda town: self.lying,
            collect=collect,
        )

    def spawn(self, kind: Kind, x: int) -> Creature:
        return self.creatures.spawn(kind, MapTile(map=ROW.id, x=x, y=2), route=())

    def run(self, seconds: float) -> None:
        for _ in range(round(seconds / STEP)):
            self.creatures.tick(STEP)


def test_a_rat_leaves_a_player_without_food_alone_and_goes_for_one_carrying_some() -> None:
    world = World()
    rat = world.spawn(RAT, 3)
    world.at = Point(10, 2, ROW.id)

    world.run(5)
    assert rat.cell == (3, 2) and world.harmed == []

    world.player.items = [RATION]
    world.run(5)
    assert world.harmed == [RAT]


def test_a_rat_scurries_home_after_a_bite_and_comes_back_once_it_has_rested() -> None:
    world = World()
    world.player.items = [RATION]
    rat = world.spawn(RAT, 3)
    world.at = Point(8, 2, ROW.id)

    for _ in range(50):
        if not world.harmed:
            world.run(STEP)
    world.run(0.5)
    assert rat.state is CreatureState.FLEEING
    world.run(2)
    assert rat.cell == rat.home and world.harmed == [RAT]
    world.run(RAT.rest)
    assert world.harmed == [RAT, RAT]


def test_a_kick_on_the_player_s_own_legs_puts_a_rat_down() -> None:
    world = World()
    rat = world.spawn(RAT, 6)
    hit = world.creatures.kickable(Kick(Point(5, 2, ROW.id), SideFacing.EAST, strength=1))
    assert hit is not None
    hit.land()
    assert rat.down is not None


def test_a_bot_ignores_a_whole_body_and_chases_a_fitted_one() -> None:
    world = World()
    bot = world.spawn(BOT, 3)
    world.at = Point(7, 2, ROW.id)

    world.run(5)
    assert bot.cell == (3, 2) and world.harmed == []

    world.player.body = FITTED
    world.run(1)
    assert bot.state is CreatureState.CHASING
    world.run(5)
    assert world.harmed and set(world.harmed) == {BOT}


def test_a_bot_shrugs_off_the_player_s_own_kick_and_is_only_knocked_back_by_bionic_legs() -> None:
    world = World()
    bot = world.spawn(BOT, 6)

    def kick(strength: float) -> None:
        hit = world.creatures.kickable(Kick(Point(5, 2, ROW.id), SideFacing.EAST, strength))
        assert hit is not None
        hit.land()

    kick(1)
    assert bot.state is not CreatureState.HURT
    kick(4)
    assert bot.state is CreatureState.HURT and bot.down is None and bot.health == math.inf
    world.run(2)
    assert bot.cell[0] > 6


def test_a_bot_drifts_to_salvage_while_the_player_is_on_its_map_and_takes_a_while_there() -> None:
    world = World({(6, 2): "near", (15, 2): "far"})
    bot = world.spawn(BOT, 3)

    world.run(30)
    assert bot.cell == (3, 2) and world.collected == []

    world.at = Point(19, 2, ROW.id)
    world.run(5)
    assert bot.cell != (6, 2) and bot.state is CreatureState.MOVING
    for _ in range(300):
        if bot.state is not CreatureState.ATTACKING:
            world.run(STEP)
    assert bot.cell == (6, 2) and world.collected == []
    world.run(COLLECTING - 0.5)
    assert world.collected == []
    world.run(1)
    assert world.collected == ["near"]


def test_the_player_beats_a_bot_to_salvage_by_picking_it_up_while_the_bot_is_taking_it() -> None:
    world = World({(6, 2): "near"})
    world.at = Point(19, 2, ROW.id)
    bot = world.spawn(BOT, 3)
    for _ in range(300):
        if bot.state is not CreatureState.ATTACKING:
            world.run(STEP)

    world.lying = {}
    world.run(COLLECTING + 1)
    assert world.collected == [] and bot.state is not CreatureState.ATTACKING


LONG = side_view("#" * 120, "#" + "." * 118 + "#", "#" + "." * 118 + "#", "#" * 120)


class Hunted:
    def __init__(self, town: TownMap, dog: tuple[int, int], at: Point) -> None:
        self.at = at
        self.harmed: list[Kind] = []
        self.creatures = Creatures(
            {town.id: town}, sense=lambda: Sight(Player(), self.at), harm=self.harmed.append
        )
        self.dog = self.creatures.spawn(DOG, MapTile(map=town.id, x=dog[0], y=dog[1]), route=())

    def run(self, seconds: float) -> None:
        for _ in range(round(seconds / STEP)):
            self.creatures.tick(STEP)


@pytest.mark.parametrize("legs", list(LEGS))
def test_a_dog_runs_down_the_player_on_every_grade_of_legs(legs: Bionic) -> None:
    run = LEGS[legs].run
    hunted = Hunted(LONG, (6, 2), Point(10, 2, LONG.id))
    for _ in range(round(8 / STEP)):
        hunted.at = Point(min(hunted.at.x + run * STEP, 117), 2, LONG.id)
        hunted.run(STEP)
    assert hunted.dog.x > 10 + run * 2, "it never caught up"
    assert len(hunted.harmed) >= 3


def test_a_dog_waits_under_the_ladder_the_player_climbs_and_never_takes_a_door() -> None:
    tunnel = side_view(*TWO_FLOORS)
    hunted = Hunted(tunnel, (2, LOWER), Point(8, LOWER, tunnel.id))
    for y in (LOWER - 1, LOWER - 2, UPPER):
        hunted.at = Point(6, y, tunnel.id)
        hunted.run(1)
    hunted.harmed.clear()
    hunted.run(5)
    assert hunted.dog.cell == (6, LOWER) and hunted.harmed == []

    for x in (14, 18):
        hunted.at = Point(x, LOWER, tunnel.id)
        hunted.run(1.5)
    assert hunted.dog.cell == (17, LOWER)
