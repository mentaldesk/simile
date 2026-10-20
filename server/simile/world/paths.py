import heapq
import math
from collections import deque
from collections.abc import Iterator, Mapping, Sequence
from itertools import pairwise
from typing import NamedTuple, Protocol

from simile.street.moves import moves
from simile.world.map import TownMap

type Cell = tuple[int, int]

STRAIGHT = ((1, 0), (-1, 0), (0, 1), (0, -1))
DIAGONAL = ((1, 1), (1, -1), (-1, 1), (-1, -1))
ROOT_2 = math.sqrt(2)
DOOR = 1.0
"""Going through a door takes as long as a step."""


class Spot(NamedTuple):
    """A tile on one of the maps."""

    map: str
    x: int
    y: int


class OnMap(Protocol):
    @property
    def map(self) -> str: ...
    @property
    def x(self) -> float: ...
    @property
    def y(self) -> float: ...


def steps(town: TownMap, cell: Cell) -> Iterator[tuple[Cell, float]]:
    """Walkable neighbours and step costs, in 8 directions without cutting corners, or on a
    side-view map by its neighbour rule, `simile.street.moves`."""
    if town.side_view:
        yield from moves(town, cell)
        return
    x, y = cell
    for dx, dy in STRAIGHT:
        if town.walkable(x + dx, y + dy):
            yield (x + dx, y + dy), 1.0
    for dx, dy in DIAGONAL:
        if town.walkable(x + dx, y + dy) and town.walkable(x + dx, y) and town.walkable(x, y + dy):
            yield (x + dx, y + dy), ROOT_2


def octile(a: Cell, b: Cell) -> float:
    dx, dy = abs(a[0] - b[0]), abs(a[1] - b[1])
    return max(dx, dy) + (ROOT_2 - 1) * min(dx, dy)


def find_path(town: TownMap, start: Cell, goal: Cell) -> list[Cell] | None:
    """The shortest path from start to goal, both included, or None if there isn't one."""
    route = find_route({town.id: town}, Spot(town.id, *start), Spot(town.id, *goal), {})
    return None if route is None else [(spot.x, spot.y) for spot in route]


def path_length(path: Sequence[tuple[float, float]]) -> float:
    return sum(math.dist(a, b) for a, b in pairwise(path))


def nearby(town: TownMap, origin: Cell) -> Iterator[tuple[Cell, int]]:
    """Every walkable cell reachable from origin and how many steps away it is, nearest first."""
    if not town.walkable(*origin):
        return
    seen = {origin}
    queue = deque([(origin, 0)])
    while queue:
        cell, depth = queue.popleft()
        yield cell, depth
        for neighbour, _ in steps(town, cell):
            if neighbour not in seen:
                seen.add(neighbour)
                queue.append((neighbour, depth + 1))


def door_ends(maps: Mapping[str, TownMap]) -> dict[Spot, Spot]:
    """Each end of every door between these maps, and the tile at its other end."""
    ends: dict[Spot, Spot] = {}
    for town in maps.values():
        for door in town.doors:
            outside = Spot(door.outside.map, door.outside.x, door.outside.y)
            inside = Spot(door.inside.map, door.inside.x, door.inside.y)
            if outside.map in maps and inside.map in maps:
                ends[outside], ends[inside] = inside, outside
    return ends


def route_length(route: Sequence[OnMap]) -> float:
    """In tiles, with each change of map a door."""
    return sum(
        math.dist((a.x, a.y), (b.x, b.y)) if a.map == b.map else DOOR for a, b in pairwise(route)
    )


def find_route(
    maps: Mapping[str, TownMap], start: Spot, goal: Spot, doors: Mapping[Spot, Spot]
) -> list[Spot] | None:
    """The shortest walk from start to goal, both included, or None if there isn't one. Each door
    is an edge between its two tiles, so going through one is two spots on different maps."""

    def walkable(spot: Spot) -> bool:
        return spot.map in maps and maps[spot.map].walkable(spot.x, spot.y)

    if not (walkable(start) and walkable(goal)):
        return None
    exits: dict[str, list[Cell]] = {}
    for end in doors:
        exits.setdefault(end.map, []).append((end.x, end.y))

    def estimate(spot: Spot) -> float:
        cell = (spot.x, spot.y)
        if spot.map == goal.map:
            return octile(cell, (goal.x, goal.y))
        return min((octile(cell, end) + DOOR for end in exits.get(spot.map, [])), default=0.0)

    def moves(spot: Spot) -> Iterator[tuple[Spot, float]]:
        if spot in doors:
            yield doors[spot], DOOR
        for cell, step in steps(maps[spot.map], (spot.x, spot.y)):
            yield Spot(spot.map, *cell), step

    came_from: dict[Spot, Spot | None] = {start: None}
    cost = {start: 0.0}
    frontier = [(estimate(start), 0.0, start)]
    while frontier:
        _, so_far, spot = heapq.heappop(frontier)
        if spot == goal:
            route = [spot]
            while (previous := came_from[route[-1]]) is not None:
                route.append(previous)
            return route[::-1]
        if so_far > cost[spot]:
            continue
        for neighbour, step in moves(spot):
            new_cost = so_far + step
            if new_cost < cost.get(neighbour, math.inf):
                cost[neighbour] = new_cost
                came_from[neighbour] = spot
                heapq.heappush(frontier, (new_cost + estimate(neighbour), new_cost, neighbour))
    return None
