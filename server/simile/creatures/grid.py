"""Where a creature can go on a side-view map, by its kind, and what it can see."""

import heapq
import math
from collections.abc import Callable, Iterator
from typing import NamedTuple

from simile.creatures.kind import Kind
from simile.schema import DoorKind, TileArea
from simile.street.moves import moves
from simile.world.map import TownMap

type Cell = tuple[int, int]

SEARCH = 4000
"""Cells a path search looks through before it settles for the nearest it found."""
FALL = 0.5
"""What each row of a drop costs a path, on top of the step off."""


class Edge(NamedTuple):
    """A move to `to`; a drop steps into `via`, open air, and falls from there."""

    to: Cell
    cost: float
    via: Cell | None = None


def covers(area: TileArea, cell: Cell) -> bool:
    x, y = cell
    return area.x <= x < area.x + area.width and area.y <= y < area.y + area.height


class Grid:
    """A map as one kind gets about it, kept inside `area` if it has one."""

    def __init__(self, town: TownMap, kind: Kind, area: TileArea | None = None) -> None:
        self.town, self.kind, self.area = town, kind, area
        ends = [end for door in town.doors for end in (door.outside, door.inside)]
        self.doors = {(end.x, end.y) for end in ends if end.map == town.id}

    def allowed(self, cell: Cell) -> bool:
        if self.area is not None and not covers(self.area, cell):
            return False
        if not self.kind.doors and cell in self.doors:
            return False
        if self.kind.flies:
            return not self.town.solid(*cell)
        return self.town.walkable(*cell) and self.takes(cell)

    def takes(self, cell: Cell) -> bool:
        """Whether its kind goes onto a ladder or stairs there, if there's one."""
        climb = self.town.climb(*cell)
        if climb is DoorKind.LADDER:
            return self.kind.climbs
        return self.kind.stairs or climb is not DoorKind.STAIRS

    def open(self, cell: Cell) -> bool:
        return not self.town.solid(*cell)

    def edges(self, cell: Cell) -> Iterator[Edge]:
        if self.kind.flies:
            yield from self._flights(cell)
            return
        for move in moves(self.town, cell):
            if self.allowed(move.cell) and self.takes(cell):
                yield Edge(move.cell, move.cost)
        if self.kind.drops and self.town.standing(*cell):
            x, y = cell
            for dx in (-1, 1):
                side = (x + dx, y)
                if self.town.walkable(*side) or self.town.solid(*side):
                    continue
                land = self.landing(side)
                if land is not None and self.allowed(land) and self.inside(side):
                    yield Edge(land, 1 + FALL * (land[1] - y), side)

    def inside(self, cell: Cell) -> bool:
        return self.area is None or covers(self.area, cell)

    def _flights(self, cell: Cell) -> Iterator[Edge]:
        x, y = cell
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                to = (x + dx, y + dy)
                if (dx or dy) and self.allowed(to):
                    if dx and dy and not (self.open((x + dx, y)) and self.open((x, y + dy))):
                        continue
                    yield Edge(to, math.hypot(dx, dy))

    def landing(self, cell: Cell) -> Cell | None:
        """Where something falling from `cell` comes to stand, if anywhere."""
        x, y = cell
        if self.town.solid(x, y):
            return None
        while not self.town.walkable(x, y):
            if self.town.solid(x, y + 1) or y >= self.town.height - 1:
                return None
            y += 1
        return (x, y)

    def ground(self, x: float, y: float) -> Cell | None:
        """The cell under a position: where its kind would stand to be there."""
        cell = (math.floor(x + 0.5), math.ceil(round(y, 6)))
        if self.kind.flies or self.town.walkable(*cell):
            return cell
        return self.landing(cell)

    def path(self, start: Cell, goal: Cell) -> list[Edge]:
        """The cheapest way to `goal`, or else to the cell it reaches nearest it."""
        if start == goal:
            return []
        frontier: list[tuple[float, float, Cell]] = [(0.0, 0.0, start)]
        came: dict[Cell, tuple[Cell, Edge] | None] = {start: None}
        cost = {start: 0.0}
        best, best_gap = start, math.dist(start, goal)
        searched = 0
        while frontier and searched < SEARCH:
            _, spent, cell = heapq.heappop(frontier)
            if spent > cost[cell]:
                continue
            searched += 1
            gap = math.dist(cell, goal)
            if gap < best_gap:
                best, best_gap = cell, gap
            if cell == goal:
                break
            for edge in self.edges(cell):
                total = spent + edge.cost
                if total < cost.get(edge.to, math.inf):
                    cost[edge.to] = total
                    came[edge.to] = (cell, edge)
                    heapq.heappush(frontier, (total + math.dist(edge.to, goal), total, edge.to))
        steps: list[Edge] = []
        cell = best
        while (step := came[cell]) is not None:
            cell, edge = step
            steps.append(edge)
        return steps[::-1]

    def nearest(self, start: Cell, good: Callable[[Cell], float | None], limit: float) -> Cell:
        """The reachable cell `good` scores lowest, or `start` if it scores none."""
        frontier: list[tuple[float, Cell]] = [(0.0, start)]
        cost = {start: 0.0}
        best, best_score = start, good(start)
        while frontier:
            spent, cell = heapq.heappop(frontier)
            if spent > cost[cell]:
                continue
            score = good(cell)
            if score is not None and (best_score is None or score < best_score):
                best, best_score = cell, score
            for edge in self.edges(cell):
                total = spent + edge.cost
                if total <= limit and total < cost.get(edge.to, math.inf):
                    cost[edge.to] = total
                    heapq.heappush(frontier, (total, edge.to))
        return best

    def run(self, cell: Cell, dx: int, cells: int) -> list[Cell]:
        """Up to `cells` cells along its row from `cell`, as far as it can go."""
        x, y = cell
        along = []
        for step in range(1, cells + 1):
            there = (x + dx * step, y)
            if not self.allowed(there) or (not self.kind.flies and self.town.climb(*there)):
                break
            along.append(there)
        return along


def sees(town: TownMap, eye: tuple[float, float], target: tuple[float, float]) -> bool:
    """Whether nothing solid is between two points in tiles, y the bottom of its row."""
    distance = math.dist(eye, target)
    samples = max(1, math.ceil(distance / 0.25))
    for i in range(1, samples):
        t = i / samples
        x = eye[0] + (target[0] - eye[0]) * t
        y = eye[1] + (target[1] - eye[1]) * t
        if town.solid(math.floor(x + 0.5), math.ceil(round(y, 6))):
            return False
    return True
