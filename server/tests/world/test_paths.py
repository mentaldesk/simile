import heapq
import math
from dataclasses import replace

import pytest

from simile.schema import Door, DoorKind, LocationKind, MapTile
from simile.world.map import TownMap, load_maps, with_every_location
from simile.world.paths import (
    DOOR,
    Cell,
    Spot,
    crossings,
    door_ends,
    find_path,
    find_route,
    nearby,
    path_length,
    route_length,
    steps,
)

MAPS = load_maps()
TOWN = with_every_location(MAPS)
DOORS = door_ends(MAPS)
CROSSINGS = crossings(MAPS)
HOUSES = [location for location in TOWN.locations if location.kind is LocationKind.HOUSE]
STREETS = [town for town in MAPS.values() if town.street]


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


def door(outside: tuple[int, int], inside: tuple[int, int]) -> Door:
    return Door(
        id="shop",
        outside=MapTile(map="street", x=outside[0], y=outside[1]),
        inside=MapTile(map="shop", x=inside[0], y=inside[1]),
    )


def shortest_route(start: Spot, goal: Spot) -> float:
    """Dijkstra over every map, each link costing as long as crossing it."""
    best = {start: 0.0}
    queue = [(0.0, start)]
    while queue:
        so_far, spot = heapq.heappop(queue)
        if spot == goal:
            return so_far
        moves = [(Spot(spot.map, *cell), step) for cell, step in steps(MAPS[spot.map], spot[1:])]
        if spot in DOORS:
            moves.append((DOORS[spot], CROSSINGS[spot][1]))
        for neighbour, step in moves:
            if so_far + step < best.get(neighbour, math.inf):
                best[neighbour] = so_far + step
                heapq.heappush(queue, (so_far + step, neighbour))
    return math.inf


@pytest.mark.parametrize("street", STREETS, ids=lambda street: street.id)
def test_finds_the_shortest_path_between_every_two_link_ends_on_a_street(street) -> None:
    ends = sorted((end.x, end.y) for end in DOORS if end.map == street.id)
    for start in ends:
        for goal in ends:
            path = find_path(street, start, goal)

            assert path is not None
            assert path[0] == start and path[-1] == goal
            for a, b in zip(path, path[1:], strict=False):
                assert b in dict(steps(street, a)), (a, b)
            assert path_length(path) == pytest.approx(shortest_distance(street, start, goal))


@pytest.mark.parametrize("goal", [(1, 0), (2, 0), (5, 5)], ids=["wall", "cut_off", "off_the_map"])
def test_finds_no_path_where_there_is_none(goal: Cell) -> None:
    assert find_path(grid(".#.", ".#.", ".#."), (0, 0), goal) is None


def test_lists_nearby_tiles_nearest_first() -> None:
    town = grid("....#..", ".......")

    assert list(nearby(town, (1, 0))) == [((1, 0), 0), ((0, 0), 1), ((2, 0), 1), ((3, 0), 2)]


def test_lists_nothing_near_a_wall() -> None:
    assert list(nearby(grid(".#."), (1, 0))) == []


@pytest.mark.parametrize("house", HOUSES, ids=lambda house: house.id)
def test_routes_from_every_house_through_the_door_to_the_coffee_shop_counter(house) -> None:
    cafe = TOWN.location("coffee_shop")
    [door] = [door for door in TOWN.doors if door.id == "coffee_shop"]
    doorstep = Spot(door.outside.map, door.outside.x, door.outside.y)
    start = Spot(house.map, house.entry.x, house.entry.y)
    goal = Spot(cafe.map, cafe.entry.x, cafe.entry.y)

    route = find_route(MAPS, start, goal, DOORS, CROSSINGS)

    assert route is not None
    assert route[0] == start and route[-1] == goal
    crossing = route.index(doorstep)
    assert route[crossing + 1] == DOORS[doorstep]
    assert route[crossing].map == "high_street"
    assert {spot.map for spot in route[crossing + 1 :]} == {cafe.map}
    for a, b in zip(route, route[1:], strict=False):
        assert DOORS.get(a) == b or (b.x, b.y) in dict(steps(MAPS[a.map], (a.x, a.y))), (a, b)
    assert route_length(route, CROSSINGS) == pytest.approx(shortest_route(start, goal))


def test_stairs_and_lifts_take_as_long_as_their_climb_or_ride() -> None:
    stairs = CROSSINGS[Spot("house_1_floor_0", 2, 2)]
    lift = CROSSINGS[Spot("gallery_floor_0", 16, 2)]
    far_lift = CROSSINGS[Spot("gallery_floor_0", 15, 2)]

    assert stairs == (DoorKind.STAIRS, pytest.approx(5))
    assert lift == (DoorKind.LIFT, pytest.approx(4 / 2.4 * 1.3))
    assert far_lift[1] > 2 * lift[1]
    assert CROSSINGS[Spot("gallery_floor_0", 2, 2)] == (DoorKind.DOOR, DOOR)


def test_the_lift_goes_straight_to_the_floor_wanted() -> None:
    painting = Spot("gallery_floor_1", 13, 2)

    route = find_route(MAPS, Spot("gallery_floor_0", 2, 2), painting, DOORS, CROSSINGS)

    assert route is not None
    assert "gallery_floor_2" not in {spot.map for spot in route}


def test_a_door_is_an_edge_between_its_two_tiles() -> None:
    maps = {
        "street": replace(grid("..."), id="street", doors=(door((1, 0), (0, 0)),)),
        "shop": replace(grid(".."), id="shop"),
    }
    doors = door_ends(maps)

    along = find_route(maps, Spot("street", 0, 0), Spot("street", 2, 0), doors)
    inside = find_route(maps, Spot("street", 0, 0), Spot("shop", 1, 0), doors)
    out = find_route(maps, Spot("shop", 1, 0), Spot("street", 2, 0), doors)

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
        Spot("street", 2, 0),
    ]
    assert route_length(inside) == route_length(out) == 2 + DOOR


def test_finds_no_route_to_a_map_without_a_door() -> None:
    maps = {"street": replace(grid("..."), id="street"), "shop": replace(grid(".."), id="shop")}
    start = Spot("street", 0, 0)

    assert find_route(maps, start, Spot("shop", 1, 0), door_ends(maps)) is None
    assert find_route(maps, start, Spot("moon", 0, 0), door_ends(maps)) is None


def test_every_door_end_leads_to_the_other() -> None:
    assert len(DOORS) == 2 * len(TOWN.doors) == len(CROSSINGS)
    for end, there in DOORS.items():
        assert DOORS[there] == end and end.map != there.map


def test_only_the_streets_are_outdoors() -> None:
    assert {town.id for town in STREETS} == {
        "banyan_row",
        "high_street",
        "kapok_walk",
        "lychee_lane",
        "metro",
        "rooftops",
        "sewers",
    }
