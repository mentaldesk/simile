import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    from simile.protocol import PlayerMoveMessage, hub_of
    from simile.schema import PLAYER_ID
    from simile.sim import world_of
    from simile.world.movement import Point, movement_of

    world, movement = world_of(app), movement_of(app)

    def on_player_move(message: PlayerMoveMessage) -> None:
        position = message.position
        if position.map not in movement.maps:
            logger.warning("Ignored a player_move onto an unknown map: %s", position)
            return
        movement.track(PLAYER_ID, Point(position.x, position.y, position.map))

    stops = [
        world.loop.register(movement),
        hub_of(app).subscribe(PlayerMoveMessage, on_player_move),
    ]
    yield
    for stop in reversed(stops):
        stop()
