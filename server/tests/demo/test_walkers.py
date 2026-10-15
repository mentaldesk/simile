import math
from datetime import UTC, datetime

import pytest

from simile.demo.walkers import PAUSE, Cell, Demo, Walker, route
from simile.protocol import Position
from simile.protocol.fixtures import fixture_snapshot
from simile.sim import STEP, EntityMoved
from simile.world.map import WALKING_SPEED, TownMap, load_map

TOWN = load_map()
SQUARE = (31, 22)
COFFEE_SHOP = (31, 11)
HOUSE_1 = (3, 11)


def steps(start: Cell, path: list[Cell]) -> list[tuple[Cell, Cell]]:
    return list(zip([start, *path], path, strict=False))


def length(start: Cell, path: list[Cell]) -> float:
    return sum(math.dist(a, b) for a, b in steps(start, path))


def ticks(system: Walker | Demo, seconds: float) -> None:
    for _ in range(round(seconds / STEP)):
        system.tick(STEP)


def test_route_walks_neighbouring_walkable_tiles_to_the_goal() -> None:
    path = route(TOWN, HOUSE_1, SQUARE)

    assert path[-1] == SQUARE
    assert all(TOWN.walkable(*cell) for cell in path)
    assert all(max(abs(a[0] - b[0]), abs(a[1] - b[1])) == 1 for a, b in steps(HOUSE_1, path))


def test_route_does_not_cut_corners() -> None:
    for (x0, y0), (x1, y1) in steps(HOUSE_1, route(TOWN, HOUSE_1, SQUARE)):
        assert TOWN.walkable(x1, y0) and TOWN.walkable(x0, y1)


def test_route_is_empty_when_already_there() -> None:
    assert route(TOWN, SQUARE, SQUARE) == []


def grid(*rows: str) -> TownMap:
    blocked = tuple(tuple(c == "#" for c in row) for row in rows)
    return TownMap("test", len(rows[0]), len(rows), blocked, ())


def test_route_is_the_shortest_walk() -> None:
    assert length((0, 0), route(grid(".....", ".....", "....."), (0, 0), (4, 2))) == (
        pytest.approx(2 + 2 * math.sqrt(2))
    )
    assert route(grid("...", ".#.", "..."), (0, 1), (2, 1)) in (
        [(0, 0), (1, 0), (2, 0), (2, 1)],
        [(0, 2), (1, 2), (2, 2), (2, 1)],
    )


def test_walker_publishes_each_tile_it_reaches_at_walking_speed() -> None:
    moved: list[tuple[float, EntityMoved]] = []
    clock = [0.0]
    walker = Walker("mei", [SQUARE, COFFEE_SHOP], TOWN, lambda e: moved.append((clock[0], e)))

    for _ in range(150):
        clock[0] += STEP
        walker.tick(STEP)

    path = route(TOWN, SQUARE, COFFEE_SHOP)
    assert [(e.x, e.y) for _, e in moved] == path
    assert all(e.entity == "mei" and isinstance(e.x, float) for _, e in moved)
    assert moved[-1][0] == pytest.approx(length(SQUARE, path) / WALKING_SPEED, abs=STEP)


def test_walker_pauses_at_each_stop_then_loops_home() -> None:
    moved: list[EntityMoved] = []
    walker = Walker("mei", [SQUARE, COFFEE_SHOP], TOWN, moved.append)
    path = route(TOWN, SQUARE, COFFEE_SHOP)
    walking = length(SQUARE, path) / WALKING_SPEED

    ticks(walker, walking + PAUSE / 2)
    assert len(moved) == len(path)
    assert walker.at == COFFEE_SHOP

    ticks(walker, PAUSE / 2 + walking + 1)
    assert walker.at == SQUARE
    assert (moved[-1].x, moved[-1].y) == SQUARE


def test_walker_waits_before_setting_off() -> None:
    moved: list[EntityMoved] = []
    walker = Walker("mei", [SQUARE, COFFEE_SHOP], TOWN, moved.append, wait=5)

    ticks(walker, 5)
    assert moved == []
    ticks(walker, 1)
    assert moved


def test_demo_walks_every_npc_and_snapshots_the_tile_each_last_reached() -> None:
    snapshot = fixture_snapshot(datetime(2026, 3, 14, 9, tzinfo=UTC))
    moved: list[EntityMoved] = []
    demo = Demo(TOWN, snapshot.entities, moved.append)

    ticks(demo, 60)

    npcs = {e.id for e in snapshot.entities if e.kind == "npc"}
    assert {e.entity for e in moved} == npcs
    for entity in demo.snapshot(snapshot).entities:
        if entity.id in npcs:
            last = next(e for e in reversed(moved) if e.entity == entity.id)
            assert entity.position == Position(x=last.x, y=last.y)
        else:
            assert entity in snapshot.entities
