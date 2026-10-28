"""How much of the lamp's charge the way between plugs takes: content/street/README.md's *Light*."""

import heapq
import math
from collections.abc import Collection, Sequence
from typing import Protocol

from simile.player.lamp import DEFAULT_LAMP, HOUR
from simile.schema import DoorKind
from simile.street.jump import JUMP, Jump
from simile.street.moves import moves

type Cell = tuple[int, int]

WALK = JUMP.run / 2
"""Tiles a second walking: the client's `PLAYER_SPEED`."""
CLIMB = {DoorKind.LADDER: 1.5, DoorKind.STAIRS: 2.0}
"""Tiles a second up or down a ladder or a flight: the client's `PLAYER_CLIMB`."""
LIGHT = HOUR / DEFAULT_LAMP.drain
"""Seconds of light in a full charge."""
SPARE = 0.15
"""Of a full charge that every run between plugs leaves at least, for waiting on what's in the
way."""
REACH = LIGHT * (1 - SPARE)
"""Seconds of light a run between plugs takes at most."""
JUMPING = 3.0
"""What a jump adds to a way's cost, on top of twice its length, so the player walks and climbs
where they can, as `tests/creatures/test_solutions.py` routes them."""


class Town(Protocol):
    def solid(self, x: int, y: int) -> bool: ...
    def climb(self, x: int, y: int) -> DoorKind | None: ...
    def walkable(self, x: int, y: int) -> bool: ...
    def standing(self, x: int, y: int) -> bool: ...
    def lit(self, x: int, y: int) -> bool: ...


class Ways:
    """The cheapest ways about a map on `jump`, walking and climbing where they can and never
    through `avoid`."""

    def __init__(self, town: Town, jump: Jump = JUMP, avoid: Collection[Cell] = ()) -> None:
        self.town, self.jump, self.avoid = town, jump, frozenset(avoid)
        self._next: dict[Cell, list[tuple[Cell, float]]] = {}
        self._from: dict[Cell, tuple[dict[Cell, float], dict[Cell, Cell]]] = {}

    def cost(self, start: Cell, end: Cell) -> float:
        return self._search(start)[0].get(end, math.inf)

    def cells(self, start: Cell, end: Cell) -> list[Cell]:
        spent, came = self._search(start)
        if end not in spent:
            raise ValueError(f"no way from {start} to {end}")
        found = [end]
        while found[-1] != start:
            found.append(came[found[-1]])
        return found[::-1]

    def tour(self, start: Cell, stops: Sequence[Cell], end: Cell) -> list[Cell]:
        """From `start` through every one of `stops`, in the cheapest order, to `end`."""
        stops = list(dict.fromkeys(stops))
        n = len(stops)
        best: dict[tuple[int, int], tuple[float, int]] = {}
        for i, stop in enumerate(stops):
            best[(1 << i, i)] = (self.cost(start, stop), -1)
        for mask in range(1, 1 << n):
            for i in range(n):
                if (mask, i) not in best:
                    continue
                spent = best[(mask, i)][0]
                for j in range(n):
                    if mask & (1 << j):
                        continue
                    key, total = (mask | 1 << j, j), spent + self.cost(stops[i], stops[j])
                    if total < best.get(key, (math.inf, -1))[0]:
                        best[key] = (total, i)
        order: list[Cell] = []
        if n:
            full = (1 << n) - 1
            i = min(range(n), key=lambda i: best[(full, i)][0] + self.cost(stops[i], end))
            mask = full
            while i != -1:
                order.append(stops[i])
                mask, i = mask & ~(1 << i), best[(mask, i)][1]
        points = [start, *order[::-1], end]
        found = [start]
        for a, b in zip(points, points[1:], strict=False):
            found += self.cells(a, b)[1:]
        return found

    def _search(self, start: Cell) -> tuple[dict[Cell, float], dict[Cell, Cell]]:
        if start not in self._from:
            spent, came, frontier = {start: 0.0}, {start: start}, [(0.0, start)]
            while frontier:
                cost, cell = heapq.heappop(frontier)
                if cost > spent[cell]:
                    continue
                for there, step in self._moves(cell):
                    if cost + step < spent.get(there, math.inf):
                        spent[there], came[there] = cost + step, cell
                        heapq.heappush(frontier, (cost + step, there))
            self._from[start] = spent, came
        return self._from[start]

    def _moves(self, cell: Cell) -> list[tuple[Cell, float]]:
        if cell not in self._next:
            found = []
            for there, cost in moves(self.town, cell, self.jump):  # type: ignore[arg-type]
                if there in self.avoid:
                    continue
                jumps = abs(there[0] - cell[0]) + abs(there[1] - cell[1]) != 1
                found.append((there, cost * (1 + jumps) + JUMPING * jumps))
            self._next[cell] = found
        return self._next[cell]


def seconds(town: Town, a: Cell, b: Cell) -> float:
    """How long the player takes from `a` to `b`: walking, climbing, or a jump at a walk."""
    kinds = {town.climb(*a), town.climb(*b)}
    up = abs(b[1] - a[1]) == 1 and abs(b[0] - a[0]) <= 1
    kind = next((k for k in (DoorKind.STAIRS, DoorKind.LADDER) if k in kinds), None)
    pace = CLIMB[kind] if up and kind is not None else WALK
    return math.dist(a, b) / pace


def runs(town: Town, cells: Sequence[Cell], plugs: Collection[Cell]) -> list[float]:
    """Seconds of light each stretch of `cells` takes, split at every plug they pass: the lamp is
    on only in the dark."""
    found, spent = [], 0.0
    for a, b in zip(cells, cells[1:], strict=False):
        if not (town.lit(*a) and town.lit(*b)):
            spent += seconds(town, a, b)
        if b in plugs:
            found.append(spent)
            spent = 0.0
    return [*found, spent]


def needless(town: Town, cells: Sequence[Cell], plugs: Collection[Cell]) -> list[Cell]:
    """The plugs on the way that it's in the lamp's reach without."""
    return [
        plug
        for plug in plugs
        if plug in cells and max(runs(town, cells, set(plugs) - {plug})) <= REACH
    ]
