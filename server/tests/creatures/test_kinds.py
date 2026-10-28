from itertools import combinations
from typing import Any

import pytest

from simile.creatures.engine import COLLECTING, STOMP_TOP, Creature, Creatures, Sight
from simile.creatures.grid import Grid
from simile.creatures.kind import Kind
from simile.creatures.kinds import BOT, DOG, RAT
from simile.schema import (
    Bionic,
    Body,
    CreatureKind,
    CreatureState,
    Item,
    ItemKind,
    MapTile,
    Player,
    TileArea,
)
from simile.street.jump import LEGS
from simile.street.plan import Spawn
from simile.world.map import TownMap
from simile.world.movement import Point

from .conftest import LOWER, TWO_FLOORS, UPPER, side_view
from .walkthrough import Leap, Step, Wait, Walk, Walkthrough

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


def land(world: World, x: float) -> None:
    """The player falling onto row 2's floor at `x`, from a row up."""
    for y in (1.0, 2 - STOMP_TOP):
        world.at = Point(x, y, ROW.id)
        world.run(STEP)


def test_landing_on_a_rat_puts_it_down_and_walking_into_one_does_not() -> None:
    world = World()
    world.player.items = [RATION]
    rat = world.spawn(RAT, 6)
    world.at = Point(4, 2, ROW.id)
    world.run(STEP)
    world.at = Point(6, 2, ROW.id)
    world.run(STEP)
    assert rat.down is None

    land(world, 6.4)
    assert rat.down is not None and world.harmed == []


@pytest.mark.parametrize("kind", [BOT, DOG], ids=["bot", "dog"])
def test_landing_on_a_bot_or_a_dog_hurts_as_running_into_it_does(kind: Kind) -> None:
    world = World()
    world.player.body = FITTED
    creature = world.spawn(kind, 6)
    land(world, 6)
    world.run(kind.think + kind.windup + STEP)

    assert creature.down is None and world.harmed == [kind]


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
    def __init__(
        self,
        town: TownMap,
        dog: tuple[int, int],
        at: Point,
        kind: Kind = DOG,
        body: Body | None = None,
    ) -> None:
        self.at = at
        self.harmed: list[Kind] = []
        player = Player(body=body or Body())
        self.creatures = Creatures(
            {town.id: town}, sense=lambda: Sight(player, self.at), harm=self.harmed.append
        )
        self.dog = self.creatures.spawn(kind, MapTile(map=town.id, x=dog[0], y=dog[1]), route=())

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


ROOM = side_view(
    "############################",
    "#..........................#",
    "#..........................#",
    "#..........................#",
    "############################",
)
"""A floor with room to jump over it, standing row 3."""
STOREYS = side_view(
    "######################",
    "#.........H..........#",
    "#.../#####H###..######",
    "#../......H..........#",
    "#....................#",
    "######################",
)
"""Stairs up from (2, 4) to (5, 1), a ladder at 10, and a hole at 14 and 15 in the upper floor."""


def walkthrough(town: TownMap, *placed: Spawn, x: float, row: int, **player: Any) -> Walkthrough:
    return Walkthrough(town, [(town.id, spawn) for spawn in placed], x, row, Player(**player))


def bot(x: int, row: int = 3) -> Spawn:
    return Spawn("bot", CreatureKind.BOT, x, row, None, 2)


def nest(*xs: int) -> list[Spawn]:
    area = TileArea(x=10, y=0, width=12, height=4)
    return [Spawn(f"rat_{x}", CreatureKind.RAT, x, 3, area, None) for x in xs]


def careless(*placed: Spawn, **player: Any) -> float:
    """The health a walk along the room past `placed` takes."""
    walk = walkthrough(ROOM, *placed, x=1.5, row=3, **player).go([Walk(26)])
    return sum(kind.damage for kind in walk.harmed)


@pytest.mark.parametrize(
    "walks",
    [
        [(bot(x),) for x in range(10, 18)],
        [nest(*xs) for xs in combinations(range(10, 22, 2), 3)],
    ],
    ids=["past a bot", "through a nest of three"],
)
def test_a_careless_walk_costs_about_a_third_of_full_health_and_three_collapse_the_player(
    walks: list[list[Spawn]],
) -> None:
    costs = [careless(*placed, body=FITTED, items=[RATION]) for placed in walks]
    each = sum(costs) / len(costs)
    assert 0.3 <= each <= 0.4 and min(costs) > 0
    assert 3 * each >= 1


@pytest.mark.parametrize("gap", [1.2, 1.6, 2.0, 2.4])
def test_a_bot_jumped_as_it_comes_does_no_harm(gap: float) -> None:
    walk = walkthrough(ROOM, bot(14), x=2, row=3, body=FITTED)

    def near(walk: Walkthrough) -> bool:
        return abs(walk.creature("bot").x - walk.x) <= gap

    def over(walk: Walkthrough) -> list[Step]:
        return [Leap(walk.x + 3.4, 3)]

    assert walk.go([Walk(25, until=near), over, Walk(25)]).harmed == []


def rows_after(start: int, way: list[tuple[int, int]]) -> set[int]:
    """The rows a bot on the lower floor is on while the player goes `way` from beside it."""
    hunted = Hunted(STOREYS, (start, 4), Point(start - 4, 4, STOREYS.id), BOT, FITTED)
    rows = set()
    for x, y in way:
        hunted.at = Point(x, y, STOREYS.id)
        for _ in range(round(2 / STEP)):
            hunted.run(STEP)
            rows.add(hunted.dog.cell[1])
    return rows


def test_a_bot_never_takes_a_ladder_or_stairs_nor_drops_off_its_floor() -> None:
    grid = Grid(STOREYS, BOT)
    for cell in (c for x in range(STOREYS.width) for y in (1, 4) if grid.allowed(c := (x, y))):
        assert all(STOREYS.climb(*e.to) is None and e.to[1] == cell[1] for e in grid.edges(cell))
    assert rows_after(16, [(12, 4), (3, 3), (4, 2), (5, 1), (9, 1)]) == {4}
    assert rows_after(7, [(3, 4), (10, 3), (10, 1), (13, 1)]) == {4}


@pytest.mark.parametrize(
    ("kind", "player"),
    [(CreatureKind.BOT, {"body": FITTED}), (CreatureKind.RAT, {"items": [RATION]})],
    ids=["bot", "rat"],
)
def test_bots_and_rats_notice_the_player_only_on_their_own_floor_and_never_on_a_ladder(
    kind: CreatureKind, player: dict[str, Any]
) -> None:
    cases = [
        ((17, 1), (13, 1, False)),
        ((17, 1), (17, 4, False)),
        ((17, 1), (19, 1, True)),
        ((13, 4), (10, 3, False)),
        ((13, 4), (11, 4, True)),
    ]
    for (sx, sy), (x, row, notices) in cases:
        spawn = Spawn("it", kind, sx, sy, None, 2)
        walk = walkthrough(STOREYS, spawn, x=x, row=row, **player).go([Wait(0.5)])
        noticed = walk.creature("it").state in {CreatureState.CHASING, CreatureState.ATTACKING}
        assert noticed == notices, (x, row)
