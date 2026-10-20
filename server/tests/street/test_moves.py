import math
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from simile.schema import DoorKind, MapTile
from simile.sim import Clock, FakeWallClock, World
from simile.street.moves import CLIMB, STAIR, WALK, moves
from simile.world import Movement, Outcome
from simile.world.map import WALKING_SPEED, TownMap
from simile.world.paths import find_path, nearby, steps

from .conftest import side_view

LADDER = side_view(
    "........",
    "........",
    "..H.....",
    "..H###..",
    "........",
    "########",
)
"""A ladder from the ground at (2, 4) up to a ledge, stepped off sideways onto (3, 2)."""
STAIRS = side_view(
    "..........",
    "..........",
    "..........",
    "..../#####",
    ".../.#####",
    ".....#####",
    "##########",
)
"""Stairs rising east from the ground at (2, 5) to the top of a block at (5, 2)."""
STEP = side_view(
    "......",
    "...###",
    "######",
)
"""A step up of one row, with no stairs."""


def neighbours(town: TownMap, cell: tuple[int, int]) -> dict[tuple[int, int], float]:
    return dict(moves(town, cell))


def test_walks_left_and_right_on_the_ground() -> None:
    assert neighbours(STEP, (1, 1)) == {(0, 1): WALK, (2, 1): WALK}
    assert neighbours(STEP, (4, 0)) == {(3, 0): WALK, (5, 0): WALK}


def test_climbs_a_ladder_straight_up_and_down_and_steps_off_sideways_at_the_top() -> None:
    assert neighbours(LADDER, (2, 4)) == {(1, 4): WALK, (3, 4): WALK, (2, 3): CLIMB}
    assert neighbours(LADDER, (2, 3)) == {(2, 2): CLIMB, (2, 4): CLIMB}
    assert neighbours(LADDER, (2, 2)) == {(2, 3): CLIMB, (3, 2): WALK}
    assert neighbours(LADDER, (3, 2)) == {(2, 2): WALK, (4, 2): WALK}
    assert find_path(LADDER, (0, 4), (5, 2)) == [
        (0, 4),
        (1, 4),
        (2, 4),
        (2, 3),
        (2, 2),
        (3, 2),
        (4, 2),
        (5, 2),
    ]


def test_climbs_stairs_diagonally_from_the_cell_below_the_first_to_the_cell_above_the_last() -> (
    None
):
    assert neighbours(STAIRS, (2, 5)) == {(1, 5): WALK, (3, 5): WALK, (3, 4): STAIR}
    assert neighbours(STAIRS, (3, 4)) == {(2, 5): STAIR, (4, 3): STAIR}
    assert neighbours(STAIRS, (4, 3)) == {(3, 4): STAIR, (5, 2): STAIR}
    assert neighbours(STAIRS, (5, 2)) == {(6, 2): WALK, (4, 3): STAIR}
    assert find_path(STAIRS, (0, 5), (7, 2)) == [
        (0, 5),
        (1, 5),
        (2, 5),
        (3, 4),
        (4, 3),
        (5, 2),
        (6, 2),
        (7, 2),
    ]


def test_a_single_stair_runs_between_the_cells_at_its_ends() -> None:
    town = side_view(
        ".....",
        ".....",
        "../##",
        ".....",
        "#####",
    )

    assert neighbours(town, (2, 2)) == {(1, 3): STAIR, (3, 1): STAIR}
    assert (2, 2) not in neighbours(town, (3, 3)), "onto it from beneath"


def test_takes_no_other_diagonal() -> None:
    under = neighbours(STAIRS, (4, 5))
    off_the_side = neighbours(STAIRS, (3, 4))

    assert (3, 4) not in under, "onto the stairs from beneath them"
    assert (4, 5) not in off_the_side, "off the side of the stairs"
    assert (3, 0) not in neighbours(STEP, (2, 1)), "up a step without stairs"
    assert find_path(STEP, (0, 1), (5, 0)) is None
    assert (3, 3) not in neighbours(LADDER, (2, 2)), "off the side of a ladder"
    assert (3, 2) not in neighbours(LADDER, (2, 3)), "onto the ledge from partway up"


def test_climbs_only_along_a_run() -> None:
    assert (2, 4) not in neighbours(STAIRS, (2, 5)), "straight up from the foot of stairs"
    assert (3, 5) not in neighbours(STAIRS, (3, 4)), "straight down off stairs"
    assert (4, 1) not in neighbours(LADDER, (4, 2)), "up from a ledge with no ladder"


@pytest.mark.parametrize("town", [LADDER, STAIRS, STEP], ids=["ladder", "stairs", "step"])
def test_never_steps_into_open_air(town: TownMap) -> None:
    for y in range(town.height):
        for x in range(town.width):
            if town.walkable(x, y):
                for (nx, ny), _ in moves(town, (x, y)):
                    assert town.walkable(nx, ny), f"({x}, {y}) to ({nx}, {ny})"
    assert (6, 2) not in neighbours(LADDER, (5, 2)), "off the end of the ledge"


def test_every_cell_of_a_run_can_be_stopped_on_and_left_both_ways() -> None:
    for town, run in ((LADDER, [(2, 3), (2, 2)]), (STAIRS, [(3, 4), (4, 3)])):
        for cell in run:
            assert town.walkable(*cell)
            assert len(neighbours(town, cell)) >= 2
            assert town.climb(*cell) is not None and not town.standing(*cell)


def test_a_resident_can_stop_partway_up_a_ladder() -> None:
    world = World(Clock(datetime(2026, 1, 1, 8, tzinfo=UTC)), FakeWallClock())
    movement = Movement(LADDER, world.bus)
    world.loop.register(movement)
    movement.place("mei", MapTile(map="street", x=0, y=4))
    walk = movement.walk_to("mei", MapTile(map="street", x=5, y=2))
    seconds = 3.2 / WALKING_SPEED
    while (world.clock.now - datetime(2026, 1, 1, 8, tzinfo=UTC)).total_seconds() < seconds:
        world.loop.tick()

    movement.stop("mei")
    for _ in range(100):
        world.loop.tick()

    assert walk.outcome is Outcome.CANCELLED
    x, y = movement.position("mei")
    assert LADDER.climb(round(x), round(y)) is DoorKind.LADDER
    assert (x, y) == (2, 2)


def test_costs_a_step_a_rung_and_the_diagonal_of_a_stair() -> None:
    assert (1.0, 1.0, math.sqrt(2)) == (WALK, CLIMB, STAIR)


def test_paths_follow_the_rule_on_side_view_maps_and_eight_directions_on_todays() -> None:
    field = side_view("....", "....", "####")
    top_down = replace(field, side_view=False, blocked=((False,) * 4,) * 3)

    assert dict(steps(field, (1, 1))) == {(0, 1): WALK, (2, 1): WALK}
    assert len(dict(steps(top_down, (1, 1)))) == 8
    assert [cell for cell, _ in nearby(field, (0, 1))] == [(0, 1), (1, 1), (2, 1), (3, 1)]
