import heapq
import math
from dataclasses import replace

import pytest

from simile.schema import VILLAGE_MAP, Door, LocationKind, MapTile
from simile.world.map import TownMap, load_map, load_maps
from simile.world.paths import (
    DOOR,
    Cell,
    Spot,
    door_ends,
    find_path,
    find_route,
    nearby,
    path_length,
    route_length,
    steps,
)

TOWN = load_map()
MAPS = load_maps()
DOORS = door_ends(MAPS)
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


def door(outside: tuple[int, int], inside: tuple[int, int]) -> Door:
    return Door(
        id="shop",
        outside=MapTile(map="street", x=outside[0], y=outside[1]),
        inside=MapTile(map="shop", x=inside[0], y=inside[1]),
    )


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


@pytest.mark.parametrize("house", HOUSES, ids=lambda house: house.id)
def test_routes_from_every_house_through_the_door_to_the_coffee_shop_counter(house) -> None:
    cafe = MAPS["coffee_shop"]
    counter = cafe.location("coffee_shop").entry
    [doorstep] = [end for end, there in DOORS.items() if there.map == cafe.id]
    mat = DOORS[doorstep]
    start = Spot(VILLAGE_MAP, house.entry.x, house.entry.y)
    goal = Spot(cafe.id, counter.x, counter.y)

    route = find_route(MAPS, start, goal, DOORS)

    assert route is not None
    assert route[0] == start and route[-1] == goal
    crossing = route.index(doorstep)
    assert route[crossing + 1] == mat
    assert {spot.map for spot in route[: crossing + 1]} == {VILLAGE_MAP}
    assert {spot.map for spot in route[crossing + 1 :]} == {cafe.id}
    outside = [(spot.x, spot.y) for spot in route[: crossing + 1]]
    inside = [(spot.x, spot.y) for spot in route[crossing + 1 :]]
    assert_walkable(TOWN, outside)
    assert_walkable(cafe, inside)
    assert route_length(route) == pytest.approx(
        shortest_distance(TOWN, outside[0], outside[-1])
        + DOOR
        + shortest_distance(cafe, inside[0], inside[-1])
    )


def test_a_door_is_an_edge_between_its_two_tiles() -> None:
    maps = {
        "street": replace(grid("...", "..."), id="street", doors=(door((1, 0), (0, 0)),)),
        "shop": replace(grid(".."), id="shop"),
    }
    doors = door_ends(maps)

    along = find_route(maps, Spot("street", 0, 0), Spot("street", 2, 0), doors)
    inside = find_route(maps, Spot("street", 0, 0), Spot("shop", 1, 0), doors)
    out = find_route(maps, Spot("shop", 1, 0), Spot("street", 2, 1), doors)

    assert along == [Spot("street", 0, 0), Spot("street", 1, 0), Spot("street", 2, 0)]
    assert inside == [
        Spot("street", 0, 0),
        Spot("street", 1, 0),
        Spot("shop", 0, 0),
        Spot("shop", 1, 0),
    ]
    assert out == [
        Spot("shop", 1, 0),
        Spot("shop", 0, 0),
        Spot("street", 1, 0),
        Spot("street", 2, 1),
    ]
    assert route_length(inside) == 2 + DOOR
    assert route_length(out) == pytest.approx(1 + DOOR + math.sqrt(2))


def test_finds_no_route_to_a_map_without_a_door() -> None:
    maps = {"street": replace(grid("..."), id="street"), "shop": replace(grid(".."), id="shop")}
    start = Spot("street", 0, 0)

    assert find_route(maps, start, Spot("shop", 1, 0), door_ends(maps)) is None
    assert find_route(maps, start, Spot("moon", 0, 0), door_ends(maps)) is None


def test_every_door_end_leads_to_the_other() -> None:
    assert len(DOORS) == 2 * len(TOWN.doors)
    for end, there in DOORS.items():
        assert DOORS[there] == end and end.map != there.map
