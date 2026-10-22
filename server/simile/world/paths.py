import heapq
import math
from collections import deque
from collections.abc import Iterator, Mapping, Sequence
from itertools import pairwise
from typing import NamedTuple, Protocol

from simile.schema import DoorKind
from simile.street.moves import moves
from simile.world.map import WALKING_SPEED, TownMap

type Cell = tuple[int, int]

ROOT_2 = math.sqrt(2)
DOOR = 1.0
"""Going through a door takes as long as a step."""
CROSSING_SPEED = {DoorKind.STAIRS: 1.3, DoorKind.LADDER: 1.0, DoorKind.LIFT: 2.4}
"""Tiles a sim second up or down stairs, a ladder or a lift between floors, as the client plays
them (`client/src/side/motion.ts`)."""


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


def steps(town: TownMap, cell: Cell, jumps: bool = False) -> Iterator[tuple[Cell, float]]:
    """Walkable neighbours and step costs, by the side view's neighbour rule,
    `simile.street.moves`."""
    yield from moves(town, cell, jumps)


def octile(a: Cell, b: Cell) -> float:
    dx, dy = abs(a[0] - b[0]), abs(a[1] - b[1])
    return max(dx, dy) + (ROOT_2 - 1) * min(dx, dy)


def find_path(town: TownMap, start: Cell, goal: Cell) -> list[Cell] | None:
    """The shortest path from start to goal, both included, or None if there isn't one."""
    route = find_route({town.id: town}, Spot(town.id, *start), Spot(town.id, *goal), {})
    return None if route is None else [(spot.x, spot.y) for spot in route]


def path_length(path: Sequence[tuple[float, float]]) -> float:
    return sum(math.dist(a, b) for a, b in pairwise(path))


def nearby(town: TownMap, origin: Cell, jumps: bool = False) -> Iterator[tuple[Cell, int]]:
    """Every walkable cell reachable from origin and how many steps away it is, nearest first."""
    if not town.walkable(*origin):
        return
    seen = {origin}
    queue = deque([(origin, 0)])
    while queue:
        cell, depth = queue.popleft()
        yield cell, depth
        for neighbour, _ in steps(town, cell, jumps):
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


def crossings(maps: Mapping[str, TownMap]) -> dict[Spot, tuple[DoorKind, float]]:
    """Each end of every link between these maps, its kind, and how long crossing it takes in
    tiles of walking: a step through a door, or the climb or ride to another floor at its
    `CROSSING_SPEED`, with the floors stacked one above the other."""
    found: dict[Spot, tuple[DoorKind, float]] = {}
    for town in maps.values():
        for door in town.doors:
            ends = [maps.get(end.map) for end in (door.outside, door.inside)]
            if ends[0] is None or ends[1] is None:
                continue
            cost = DOOR
            if door.kind is not DoorKind.DOOR:
                low, high = (
                    (end.x, end.y - (town.floor or 0) * town.height)
                    for end, town in zip((door.outside, door.inside), ends, strict=True)
                )
                dx, dy = abs(high[0] - low[0]), abs(high[1] - low[1])
                length = dx + dy if door.kind is DoorKind.LIFT else math.hypot(dx, dy)
                cost = max(length / CROSSING_SPEED[door.kind] * WALKING_SPEED, DOOR)
            for end in (door.outside, door.inside):
                found[Spot(end.map, end.x, end.y)] = (door.kind, cost)
    return found


def route_length(
    route: Sequence[OnMap], costs: Mapping[Spot, tuple[DoorKind, float]] | None = None
) -> float:
    """In tiles, with each change of map a door, or with `costs`, as long as crossing that link."""

    def across(a: OnMap) -> float:
        spot = Spot(a.map, round(a.x), round(a.y))
        return costs[spot][1] if costs and spot in costs else DOOR

    return sum(
        math.dist((a.x, a.y), (b.x, b.y)) if a.map == b.map else across(a)
        for a, b in pairwise(route)
    )


def find_route(
    maps: Mapping[str, TownMap],
    start: Spot,
    goal: Spot,
    doors: Mapping[Spot, Spot],
    costs: Mapping[Spot, tuple[DoorKind, float]] | None = None,
    jumps: bool = False,
) -> list[Spot] | None:
    """The shortest walk from start to goal, both included, or None if there isn't one. Each door
    is an edge between its two tiles, so going through one is two spots on different maps. It
    costs a step, or with `costs`, as long as crossing that link takes."""

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
            yield doors[spot], costs[spot][1] if costs and spot in costs else DOOR
        for cell, step in steps(maps[spot.map], (spot.x, spot.y), jumps):
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
