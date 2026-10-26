import logging
from collections.abc import Callable, Sequence
from typing import NamedTuple

from starlette.applications import Starlette

from simile.player.where import here
from simile.schema import Player, SideFacing
from simile.sim import Clock
from simile.street.jump import jump_of
from simile.world.movement import Movement, Point

logger = logging.getLogger(__name__)

REACH = 1.2
"""Tiles in front of where the player stands that a kick reaches."""


class Kick(NamedTuple):
    """The player kicking `facing` from `at`, `strength` times as hard as their own legs kick,
    reaching `reach` tiles."""

    at: Point
    facing: SideFacing
    strength: float
    reach: float = REACH


class Hit(NamedTuple):
    """Something a kick would land on, `distance` tiles from the player."""

    distance: float
    land: Callable[[], object]


type Kickable = Callable[[Kick], Hit | None]


def kickables_of(app: Starlette) -> list[Kickable]:
    """What a kick can hit, such as the creatures. Other modules add to it."""
    if not hasattr(app.state, "kickables"):
        app.state.kickables = []
    return app.state.kickables


class Kicks:
    """The player's kick, which lands on the nearest thing it hits."""

    def __init__(
        self, player: Player, movement: Movement, clock: Clock, kickables: Sequence[Kickable]
    ) -> None:
        self.player = player
        self.movement = movement
        self.clock = clock
        self.kickables = kickables

    def kick(self, facing: SideFacing) -> bool:
        """Kicks from where the server keeps them, off a side-view map never. Whether it hit."""
        at = here(self.movement)
        town = self.movement.maps.get(at.map) if at is not None else None
        if at is None or town is None or town.kind is None:
            return False
        kick = Kick(at, facing, jump_of(self.player.body).kick)
        hits = [hit for kickable in self.kickables if (hit := kickable(kick)) is not None]
        if not hits:
            return False
        min(hits, key=lambda hit: hit.distance).land()
        logger.info("%s  The player kicks %s and hits", self.clock, facing)
        return True
