from simile.schema import PLAYER_ID, Id, Location
from simile.world.movement import Movement, Point


def here(movement: Movement) -> Point | None:
    """Where the player is, once a client has said."""
    return movement.entities().get(PLAYER_ID)


def location(movement: Movement, place: Id) -> Location | None:
    try:
        return movement.town.location(place)
    except KeyError:
        return None
