import math
from collections.abc import Iterator
from typing import TYPE_CHECKING, NamedTuple

from simile.schema import DoorKind

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


def moves(town: "TownMap", cell: Cell) -> Iterator[Move]:
    """The side-view neighbour rule: left and right between walkable cells on one row, and up and
    down only along a climbable run, straight on a ladder and diagonally on stairs, to the cells
    at its ends. A resident can stop on any cell of a run."""
    x, y = cell
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
