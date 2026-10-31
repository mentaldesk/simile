import math
from collections.abc import Iterator
from typing import TYPE_CHECKING, NamedTuple

from simile.schema import DoorKind
from simile.street.jump import JUMP, Jump

if TYPE_CHECKING:
    from simile.world.map import TownMap

type Cell = tuple[int, int]

WALK = 1.0
"""A step left or right."""
CLIMB = 1.0
"""A rung up or down a ladder."""
STAIR = math.sqrt(2)
"""A stair up or down, one along and one up."""
RISES = ((1, -1), (-1, -1))
"""The diagonals a flight of stairs can run along: up to the east, and up to the west."""
DIAGONALS = (*RISES, (-1, 1), (1, 1))
ON_THE_WAY = 0.02
"""Tiles off the line between two cells a position mid-step can be, as the client rounds it."""


class Move(NamedTuple):
    cell: Cell
    cost: float


def moves(town: "TownMap", cell: Cell, jumps: bool | Jump = False) -> Iterator[Move]:
    """The side-view neighbour rule: left and right between walkable cells on one row, and up and
    down only along a climbable run, straight on a ladder and diagonally on stairs, to the cells
    at its ends. A resident can stop on any cell of a run."""
    x, y = cell
    if jumps:
        yield from _jumps(town, cell, JUMP if jumps is True else jumps)
    here = town.climb(x, y)
    for dx in (-1, 1):
        if town.walkable(x + dx, y):
            yield Move((x + dx, y), WALK)
    for dy in (-1, 1):
        there = town.climb(x, y + dy)
        on_ladder = DoorKind.LADDER in (here, there) and DoorKind.STAIRS not in (here, there)
        if on_ladder and town.walkable(x, y + dy):
            yield Move((x, y + dy), CLIMB)
    for dx, dy in DIAGONALS:
        nx, ny = x + dx, y + dy
        there = town.climb(nx, ny)
        if DoorKind.STAIRS not in (here, there) or DoorKind.LADDER in (here, there):
            continue
        sx, sy = (x, y) if here is DoorKind.STAIRS else (nx, ny)
        rise = (dx, dy) if dy < 0 else (-dx, -dy)
        if rise in _flights(town, sx, sy) and town.walkable(nx, ny):
            yield Move((nx, ny), STAIR)


def _flights(town: "TownMap", x: int, y: int) -> tuple[Cell, ...]:
    """The rises the stairs on (x, y) run along: towards the next stair, or for a single stair,
    between the two walkable cells at its ends."""

    def stairs(dx: int, dy: int) -> bool:
        return town.climb(x + dx, y + dy) is DoorKind.STAIRS

    def ends(dx: int, dy: int) -> bool:
        return town.walkable(x + dx, y + dy)

    linked = tuple(r for r in RISES if stairs(*r) or stairs(-r[0], -r[1]))
    return linked or tuple(r for r in RISES if ends(*r) and ends(-r[0], -r[1]))


def _jumps(town: "TownMap", cell: Cell, jump: Jump) -> Iterator[Move]:
    """A jump through open air to a standing cell up to `jump.cells` along, `jump.rows` up."""
    x, y = cell
    if not town.standing(x, y):
        return
    for dx in (d for d in range(-jump.cells, jump.cells + 1) if d):
        nx = x + dx
        for ny in range(y - jump.rows, town.height):
            if town.solid(nx, ny):
                if ny > y:
                    break
                continue
            end = (nx, ny)
            if (abs(dx) > 1 or ny != y) and town.standing(nx, ny) and _clear(town, cell, end):
                rise = _rise(town, cell, end, jump)
                if y - ny <= math.floor(rise) and abs(dx) <= jump.along(rise):
                    yield Move(end, math.hypot(dx, ny - y))


def _rise(town: "TownMap", start: Cell, end: Cell, jump: Jump) -> float:
    """How high above `start` a jump to `end` can rise before its head meets something solid."""
    (x, y), (nx, ny) = start, end
    top = min(y, ny) - 1
    room = 0
    while room <= jump.rows and not any(
        town.solid(cx, top - room - 1) for cx in range(min(x, nx), max(x, nx) + 1)
    ):
        room += 1
    return min(jump.rise, y + 1 - jump.body - top + room)


def _clear(town: "TownMap", start: Cell, end: Cell) -> bool:
    (x, y), (nx, ny) = start, end
    top = min(y, ny) - 1
    step = 1 if nx > x else -1
    path = [(x, r) for r in range(top, y)]
    path += [(cx, r) for cx in range(x, nx + step, step) for r in (top, top + 1)]
    path += [(nx, r) for r in range(top, ny + 1)]
    return not any(town.solid(cx, r) for cx, r in path)


def possible(
    town: "TownMap", x: float, y: float, last: tuple[float, float] | None, jump: Jump = JUMP
) -> bool:
    """Whether a `player_move` to (x, y) is kept, after `last`: docs/protocol.md's rule."""
    cx, cy = math.floor(x + 0.5), math.ceil(round(y, 6))
    if town.walkable(cx, cy) or _between(town, x, y):
        return True
    if town.solid(cx, cy) or not _lands(town, cx, cy):
        return False
    falling = last is not None and y > last[1] and abs(x - last[0]) <= jump.reach
    return falling or _within_a_jump(town, x, y, jump)


def _between(town: "TownMap", x: float, y: float) -> bool:
    """On the way from one cell to the next by a step or a climb."""
    corners = {(math.floor(x), math.floor(y)), (math.ceil(x), math.ceil(y))}
    corners |= {(math.floor(x), math.ceil(y)), (math.ceil(x), math.floor(y))}
    for a in corners:
        for (bx, by), _ in moves(town, a) if town.walkable(*a) else ():
            dx, dy = bx - a[0], by - a[1]
            t = min(max(((x - a[0]) * dx + (y - a[1]) * dy) / (dx * dx + dy * dy), 0), 1)
            if math.dist((x, y), (a[0] + t * dx, a[1] + t * dy)) <= ON_THE_WAY:
                return True
    return False


def _lands(town: "TownMap", x: int, y: int) -> bool:
    """Falling straight down from (x, y) comes to somewhere to stand."""
    while y < town.height - 1 and not town.solid(x, y + 1):
        y += 1
    return town.standing(x, y)


def _within_a_jump(town: "TownMap", x: float, y: float, jump: Jump) -> bool:
    """Up to `jump.rise` above a standing cell within `jump.reach`, or half a row below it."""
    reach = math.floor(jump.reach)
    rows = range(math.ceil(y - 0.5), math.floor(y + jump.rise) + 1)
    return any(
        town.standing(sx, sy) and abs(sx - x) <= jump.reach
        for sx in range(math.floor(x) - reach, math.ceil(x) + reach + 1)
        for sy in rows
    )
