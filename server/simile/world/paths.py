import heapq
import math
from collections import deque
from collections.abc import Iterator, Sequence
from itertools import pairwise

from simile.world.map import TownMap

type Cell = tuple[int, int]

STRAIGHT = ((1, 0), (-1, 0), (0, 1), (0, -1))
DIAGONAL = ((1, 1), (1, -1), (-1, 1), (-1, -1))
ROOT_2 = math.sqrt(2)


def steps(town: TownMap, cell: Cell) -> Iterator[tuple[Cell, float]]:
    """Walkable neighbours and step costs, in 8 directions without cutting corners."""
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
    if not (town.walkable(*start) and town.walkable(*goal)):
        return None
    came_from: dict[Cell, Cell | None] = {start: None}
    cost = {start: 0.0}
    frontier = [(octile(start, goal), 0.0, start)]
    while frontier:
        _, so_far, cell = heapq.heappop(frontier)
        if cell == goal:
            path = [cell]
            while (previous := came_from[path[-1]]) is not None:
                path.append(previous)
            return path[::-1]
        if so_far > cost[cell]:
            continue
        for neighbour, step in steps(town, cell):
            new_cost = so_far + step
            if new_cost < cost.get(neighbour, math.inf):
                cost[neighbour] = new_cost
                came_from[neighbour] = cell
                heapq.heappush(frontier, (new_cost + octile(neighbour, goal), new_cost, neighbour))
    return None


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
