import heapq
import math

import pytest

from simile.schema import LocationKind
from simile.world.map import TownMap, load_map
from simile.world.paths import Cell, find_path, nearby, path_length, steps

TOWN = load_map()
HOUSES = [location for location in TOWN.locations if location.kind is LocationKind.HOUSE]


def grid(*rows: str) -> TownMap:
    blocked = tuple(tuple(cell == "#" for cell in row) for row in rows)
    return TownMap("test", len(rows[0]), len(rows), blocked, ())


def shortest_distance(town: TownMap, start: Cell, goal: Cell) -> float:
    best = {start: 0.0}
    queue = [(0.0, start)]
    while queue:
        so_far, cell = heapq.heappop(queue)
        if cell == goal:
            return so_far
        for neighbour, step in steps(town, cell):
            if so_far + step < best.get(neighbour, math.inf):
                best[neighbour] = so_far + step
                heapq.heappush(queue, (so_far + step, neighbour))
    return math.inf


def assert_walkable(town: TownMap, path: list[Cell]) -> None:
    for (x, y), (nx, ny) in zip(path, path[1:], strict=False):
        assert town.walkable(nx, ny)
        assert max(abs(nx - x), abs(ny - y)) == 1
        assert town.walkable(nx, y) and town.walkable(x, ny), "cut a corner"


@pytest.mark.parametrize("house", HOUSES, ids=lambda house: house.id)
def test_finds_the_shortest_path_from_every_house_to_the_coffee_shop(house) -> None:
    start = (house.entry.x, house.entry.y)
    coffee_shop = TOWN.location("coffee_shop").entry
    goal = (coffee_shop.x, coffee_shop.y)

    path = find_path(TOWN, start, goal)

    assert path is not None
    assert path[0] == start and path[-1] == goal
    assert_walkable(TOWN, path)
    assert path_length(path) == pytest.approx(shortest_distance(TOWN, start, goal))


def test_walks_diagonally_in_the_open() -> None:
    path = find_path(grid("...", "...", "..."), (0, 0), (2, 2))

    assert path == [(0, 0), (1, 1), (2, 2)]
    assert path_length(path) == pytest.approx(2 * math.sqrt(2))


@pytest.mark.parametrize("rows", [(".#", ".."), ("..", "#.")], ids=["above", "beside"])
def test_never_cuts_a_corner(rows: tuple[str, str]) -> None:
    town = grid(*rows)

    path = find_path(town, (0, 0), (1, 1))

    assert path is not None and len(path) == 3
    assert_walkable(town, path)


@pytest.mark.parametrize("goal", [(1, 0), (2, 0), (5, 5)], ids=["wall", "cut_off", "off_the_map"])
def test_finds_no_path_where_there_is_none(goal: Cell) -> None:
    assert find_path(grid(".#.", ".#.", ".#."), (0, 0), goal) is None


def test_lists_nearby_tiles_nearest_first() -> None:
    town = grid("...#.", ".....", ".....")

    found = list(nearby(town, (1, 1)))

    depths = {cell: depth for cell, depth in found}
    assert found[0] == ((1, 1), 0)
    assert [depth for _, depth in found] == sorted(depths.values())
    assert {cell for cell, depth in found if depth == 1} == {
        (0, 0),
        (1, 0),
        (2, 0),
        (0, 1),
        (2, 1),
        (0, 2),
        (1, 2),
        (2, 2),
    }
    assert depths[(4, 0)] == 4
    assert set(depths) == {(x, y) for x in range(5) for y in range(3)} - {(3, 0)}


def test_lists_nothing_near_a_wall() -> None:
    assert list(nearby(grid(".#."), (1, 0))) == []
