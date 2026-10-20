import math
from collections.abc import Mapping

from simile.schema import Id
from simile.world import Movement, Point
from simile.world.map import TownMap


def apart(maps: Mapping[str, TownMap], here: Point, there: Point) -> float:
    """How far apart two people are to hear or talk to each other, in tiles: along x on a
    side-view map, in a straight line on today's, and out of reach on different maps."""
    if here.map != there.map:
        return math.inf
    town = maps.get(here.map)
    if town is not None and town.side_view:
        return abs(there.x - here.x)
    return math.dist(here, there)


def between(movement: Movement, a: Id, b: Id) -> float:
    """`apart` for two entities. Raises KeyError if either isn't placed, as
    `Movement.distance` does."""
    return apart(movement.maps, movement.position(a), movement.position(b))
