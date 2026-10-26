import json
import math
from datetime import UTC, datetime
from pathlib import Path

import pytest

from simile.schema import Bionic, Body, DoorKind, MapTile
from simile.sim import Clock, FakeWallClock, World
from simile.street.jump import (
    FEET,
    GRADES,
    JUMP,
    KITS,
    LEGS,
    NEEDS,
    OWN_JUMP,
    jump_of,
    jump_table,
    meets,
)
from simile.street.moves import CLIMB, STAIR, WALK, moves, possible
from simile.world import Movement, Outcome
from simile.world.map import STREET_DIR, WALKING_SPEED, TownMap, load_maps
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


def test_paths_follow_the_rule() -> None:
    field = side_view("....", "....", "####")

    assert dict(steps(field, (1, 1))) == {(0, 1): WALK, (2, 1): WALK}
    assert [cell for cell, _ in nearby(field, (0, 1))] == [(0, 1), (1, 1), (2, 1), (3, 1)]


ROOFS = side_view(
    "..............................",
    "..............................",
    "..............................",
    "..............................",
    "..............................",
    "#####.#####..#####...###....##",
    "..............................",
    "..............................",
    "..............................",
    "##############################",
)
"""Rooftops on row 5 with gaps of one, two, three and four cells, over a lane on row 8."""
LEDGES = side_view(
    "..........",
    "..........",
    "..........",
    "......####",
    "..........",
    "...###....",
    "..........",
    "##########",
)
"""A ledge two rows up from the ground, and another two rows above that."""


def jumps(town: TownMap, cell: tuple[int, int]) -> set[tuple[int, int]]:
    return set(dict(moves(town, cell, jumps=True))) - set(neighbours(town, cell))


def test_jumps_only_for_the_player() -> None:
    assert (6, 4) not in neighbours(ROOFS, (4, 4))
    assert (6, 4) in jumps(ROOFS, (4, 4))


def test_jumps_gaps_of_up_to_three_cells_along_a_row_and_no_more() -> None:
    assert JUMP.cells == 4
    assert (6, 4) in jumps(ROOFS, (4, 4))
    assert (13, 4) in jumps(ROOFS, (10, 4))
    assert (21, 4) in jumps(ROOFS, (17, 4))
    assert (28, 4) not in jumps(ROOFS, (23, 4))


def test_jumps_up_to_two_rows_up_and_down_any_way() -> None:
    assert (3, 4) in jumps(LEDGES, (2, 6))
    assert (6, 2) in jumps(LEDGES, (5, 4))
    assert (6, 2) not in jumps(LEDGES, (4, 6))
    assert {(1, 6), (5, 4), (2, 6)} <= jumps(LEDGES, (5, 4)) | jumps(LEDGES, (6, 2))
    assert (6, 6) not in jumps(LEDGES, (5, 4)), "its head hits the ledge above"


def test_jumps_through_open_air_only() -> None:
    walled = side_view(
        "........",
        "........",
        "........",
        "...#....",
        "...#....",
        "##.#.###",
        "########",
    )
    assert (5, 4) not in jumps(walled, (1, 4))
    assert jumps(walled, (2, 5)) == {(0, 4), (1, 4)}


def test_paths_jump_for_the_player_only() -> None:
    assert find_path(ROOFS, (2, 4), (14, 4)) is None
    assert (14, 4) not in dict(nearby(ROOFS, (2, 4)))
    assert (14, 4) in dict(nearby(ROOFS, (2, 4), jumps=True))


@pytest.mark.parametrize(
    ("x", "y"),
    [(2, 4), (2.4, 4), (5, 4), (5.6, 2.1), (5, 4 - JUMP.rise + 0.05), (8, 2.5), (13.2, 6.7)],
)
def test_the_player_can_be_on_the_roofs_or_in_the_air_within_a_jump(x: float, y: float) -> None:
    assert possible(ROOFS, x, y, None)


@pytest.mark.parametrize(
    ("x", "y", "why"),
    [
        (2, 5, "in a roof"),
        (2, 9, "in the ground"),
        (-1, 4, "off the map"),
        (40, 4, "off the map"),
        (5, 4 - JUMP.rise - 0.6, "higher than any jump"),
        (5, -1, "above the map"),
    ],
)
def test_the_player_cant_be_where_nobody_could_be(x: float, y: float, why: str) -> None:
    assert not possible(ROOFS, x, y, None), why


def test_a_fall_from_higher_than_a_jump_is_kept_as_it_comes_down() -> None:
    tower = side_view(
        "...............",
        "###............",
        "...............",
        "...............",
        "...............",
        "...............",
        "...............",
        "...............",
        "...............",
        "...............",
        "###############",
    )
    last = (2.0, 0.0)
    for x, y in [(3.6, 0.4), (5.0, 1.8), (7.0, 4.2), (9.0, 7.5), (10.4, 9)]:
        assert possible(tower, x, y, last), (x, y)
        last = (x, y)
    assert not possible(tower, 9.0, 5.0, None)
    assert not possible(tower, 9.0, 5.0, (9.0, 6.0))


def test_a_fall_is_kept_only_within_a_jump_of_the_last_position_along_the_row() -> None:
    tower = side_view(
        "........................",
        "###.....................",
        *["........................"] * 8,
        "########################",
    )
    assert possible(tower, 8.0, 5.0, (3.0, 4.0))
    assert not possible(tower, 20.0, 5.0, (3.0, 4.0))
    assert not possible(tower, 3.0 + JUMP.reach + 0.1, 5.0, (3.0, 4.0))


POSITIONS = json.loads((Path(__file__).parent / "positions.json").read_text())
"""The client's sends on several maps, and places nobody could be: `jump.test.ts` checks it too."""
STREETS = load_maps(STREET_DIR)


def test_the_spring_feet_jump_two_rows_higher_by_the_lift() -> None:
    metro, feet = STREETS["metro"], GRADES[Bionic.SPRING_FEET]

    assert jump_of(Body()) is JUMP and jump_of(Body(feet=Bionic.SPRING_FEET)) is feet
    assert not possible(metro, 100, 11.9, None) and possible(metro, 100, 11.9, None, feet)


@pytest.mark.parametrize(
    ("legs", "feet", "rows", "run", "cells", "kick"),
    [
        (None, None, 2, 5.2, 4, 1.0),
        (Bionic.BIONIC_LEGS, None, 2, 7.8, 6, 2.0),
        (Bionic.BIONIC_LEGS_2, None, 2, 10.4, 8, 3.0),
        (Bionic.BIONIC_LEGS_3, None, 2, 13.0, 10, 4.0),
        (None, Bionic.SPRING_FEET, 4, 5.2, 5, 1.0),
        (None, Bionic.SPRING_FEET_2, 6, 5.2, 6, 1.0),
        (Bionic.BIONIC_LEGS, Bionic.SPRING_FEET, 4, 7.8, 8, 2.0),
        (Bionic.BIONIC_LEGS_2, Bionic.SPRING_FEET_2, 6, 10.4, 13, 3.0),
        (Bionic.BIONIC_LEGS, Bionic.SPRING_FEET_2, 6, 7.8, 9, 2.0),
    ],
)
def test_each_grade_jumps_as_high_and_as_far_and_runs_as_fast_as_its_table_says(
    legs: Bionic | None, feet: Bionic | None, rows: int, run: float, cells: int, kick: float
) -> None:
    jump = jump_of(Body(legs=legs or "present", feet=feet or "present"))
    table = jump_table()
    name = "+".join(b for b in (legs, feet) if b)
    row = table | table["kits"][name] if name else table

    assert (jump.rows, jump.run, jump.cells, jump.kick) == (rows, run, cells, kick)
    assert rows < jump.rise < rows + 1 and jump.gravity == pytest.approx(JUMP.gravity)
    assert jump.reach == pytest.approx(row["reach"], abs=1e-3)
    assert (row["rise"], row["rows"], row["run"], row["cells"]) == (jump.rise, rows, run, cells)
    assert row["kick"] == kick


def test_the_legs_run_faster_and_kick_harder_and_the_feet_rise_higher_by_grade() -> None:
    legs, feet = list(LEGS.values()), list(FEET.values())

    assert all(jump.rise == JUMP.rise for jump in legs)
    assert JUMP.run < legs[0].run < legs[1].run < legs[2].run
    assert JUMP.kick < legs[0].kick < legs[1].kick < legs[2].kick
    assert all((jump.run, jump.kick) == (JUMP.run, JUMP.kick) for jump in feet)
    assert JUMP.rows + 2 <= feet[0].rows and feet[0].rows + 2 <= feet[1].rows


def test_the_legs_and_the_feet_together_jump_on_the_best_of_each() -> None:
    both = jump_of(Body(legs=Bionic.BIONIC_LEGS, feet=Bionic.SPRING_FEET_2))

    assert (both.rise, both.run, both.kick) == (6.3, 7.8, 2.0)
    assert set(KITS.values()) == {jump_of(Body(legs=a, feet=b)) for a, b in _bodies()}


def _bodies() -> list[tuple[Bionic | str, Bionic | str]]:
    every_legs = ["present", *(b for b in Bionic if "legs" in b.replaces)]
    return [(legs, feet) for legs in every_legs for feet in ["present", *FEET]]


def test_a_place_is_in_reach_of_the_legs_that_rise_as_high_and_run_as_fast_as_it_needs() -> None:
    assert all(meets(jump, OWN_JUMP) for jump in NEEDS.values())
    assert all(meets(KITS["bionic_legs_3+spring_feet_2"], needs) for needs in NEEDS)
    assert meets(FEET[Bionic.SPRING_FEET_2], Bionic.SPRING_FEET)
    assert meets(LEGS[Bionic.BIONIC_LEGS_2], Bionic.BIONIC_LEGS)
    assert not meets(LEGS[Bionic.BIONIC_LEGS_3], Bionic.SPRING_FEET)
    assert not meets(FEET[Bionic.SPRING_FEET_2], Bionic.BIONIC_LEGS)
    assert not meets(JUMP, Bionic.SPRING_FEET)


GAP = (
    "................",
    "................",
    "................",
    "................",
    "####.....#######",
    "................",
    "################",
)
"""A five-cell gap between two ledges, over a floor."""


def test_a_roof_low_over_a_gap_leaves_only_the_faster_legs_across() -> None:
    roofed, open_air = side_view("#" * 16, *GAP), side_view(*["." * 16] * 4, *GAP)

    for kit, jump in KITS.items():
        across = (9, 4) in dict(moves(roofed, (3, 4), jump))
        assert across is (jump.run > JUMP.run), kit
    assert (9, 4) not in dict(moves(roofed, (3, 4), True))
    assert (9, 7) in dict(moves(open_air, (3, 7), GRADES[Bionic.SPRING_FEET_2]))


@pytest.mark.parametrize("case", POSITIONS, ids=lambda c: f"{c['why']} at {c['x']}, {c['y']}")
def test_keeps_the_clients_sends_and_ignores_where_nobody_could_be(case: dict) -> None:
    last = tuple(case["last"]) if case["last"] else None
    jump = jump_of(Body(legs=case.get("legs", "present"), feet=case.get("feet", "present")))
    assert possible(STREETS[case["map"]], case["x"], case["y"], last, jump) is case["kept"]


def test_keeps_a_climb_up_or_down_stairs_all_the_way() -> None:
    banyan = STREETS["banyan_row"]
    for i in range(61):
        t = i / 20
        assert possible(banyan, 53 + t, 15 + t, None), (53 + t, 15 + t)
        assert possible(banyan, 53 + t + 0.01, 15 + t, None), (53 + t + 0.01, 15 + t)
