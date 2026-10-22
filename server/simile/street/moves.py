import math
from collections.abc import Iterator
from typing import TYPE_CHECKING, NamedTuple

from simile.schema import DoorKind
from simile.street.jump import JUMP

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


class Move(NamedTuple):
    cell: Cell
    cost: float


def moves(town: "TownMap", cell: Cell, jumps: bool = False) -> Iterator[Move]:
    """The side-view neighbour rule: left and right between walkable cells on one row, and up and
    down only along a climbable run, straight on a ladder and diagonally on stairs, to the cells
    at its ends. A resident can stop on any cell of a run. With `jumps`, for the player, a jump
    from a standing cell too."""
    x, y = cell
    if jumps:
        yield from _jumps(town, cell)
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


def _jumps(town: "TownMap", cell: Cell) -> Iterator[Move]:
    """A run jump to a standing cell up to `JUMP.cells` along the row and `JUMP.rows` up, or down
    any way, through open air: up from where it takes off, along over the higher end with room
    for the head, and down onto where it lands."""
    x, y = cell
    if not town.standing(x, y):
        return
    for dx in (d for d in range(-JUMP.cells, JUMP.cells + 1) if d):
        nx = x + dx
        for ny in range(y - JUMP.rows, town.height):
            if town.solid(nx, ny):
                if ny > y:
                    break
                continue
            if (abs(dx) > 1 or ny != y) and town.standing(nx, ny) and _clear(town, cell, (nx, ny)):
                yield Move((nx, ny), math.hypot(dx, ny - y))


def _clear(town: "TownMap", start: Cell, end: Cell) -> bool:
    (x, y), (nx, ny) = start, end
    top = min(y, ny) - 1
    step = 1 if nx > x else -1
    path = [(x, r) for r in range(top, y)]
    path += [(cx, r) for cx in range(x, nx + step, step) for r in (top, top + 1)]
    path += [(nx, r) for r in range(top, ny + 1)]
    return not any(town.solid(cx, r) for cx, r in path)


def possible(town: "TownMap", x: float, y: float, last: tuple[float, float] | None) -> bool:
    """Whether the player can be at (x, y): somewhere to stand or climb, or mid-step, or mid-air
    in open air over somewhere to land, within the farthest jump from somewhere to stand, or
    lower than `last`, the last position kept on this map, and within the jump's reach of it
    along the row, as in a fall from any height."""
    cx, cy = math.floor(x + 0.5), math.ceil(round(y, 6))
    if town.walkable(cx, cy):
        return True
    if town.solid(cx, cy) or not _lands(town, cx, cy):
        return False
    falling = last is not None and y > last[1] and abs(x - last[0]) <= JUMP.reach
    return falling or _within_a_jump(town, x, y)


def _lands(town: "TownMap", x: int, y: int) -> bool:
    """Falling straight down from (x, y) comes to somewhere to stand, inside the map."""
    while y < town.height - 1 and not town.solid(x, y + 1):
        y += 1
    return town.standing(x, y)


def _within_a_jump(town: "TownMap", x: float, y: float) -> bool:
    """No higher than `JUMP.rise` above a standing cell within `JUMP.reach` along the row, and not
    below it by more than half a row, where coyote time can start a jump."""
    reach = math.floor(JUMP.reach)
    rows = range(math.ceil(y - 0.5), math.floor(y + JUMP.rise) + 1)
    return any(
        town.standing(sx, sy) and abs(sx - x) <= JUMP.reach
        for sx in range(math.floor(x) - reach, math.ceil(x) + reach + 1)
        for sy in rows
    )
