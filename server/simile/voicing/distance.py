import math

from simile.schema import Id
from simile.world import Movement, Point


def apart(here: Point, there: Point) -> float:
    """How far apart two people are to hear or talk to each other, in tiles: along x, the street,
    and out of reach on different maps."""
    if here.map != there.map:
        return math.inf
    return abs(there.x - here.x)


def between(movement: Movement, a: Id, b: Id) -> float:
    """`apart` for two entities. Raises KeyError if either isn't placed, as
    `Movement.distance` does."""
    return apart(movement.position(a), movement.position(b))
