import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette


@asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    from simile.protocol import PlayerMoveMessage, hub_of
    from simile.schema import PLAYER_ID
    from simile.sim import world_of
    from simile.world.demo import DEMO_ENV, WalkDemo
    from simile.world.movement import Point, movement_of

    world, movement = world_of(app), movement_of(app)

    def on_player_move(message: PlayerMoveMessage) -> None:
        position = message.position
        movement.track(PLAYER_ID, Point(position.x, position.y, position.map))

    stops = [
        world.loop.register(movement),
        hub_of(app).subscribe(PlayerMoveMessage, on_player_move),
    ]
    if os.environ.get(DEMO_ENV):
        stops.append(world.loop.register(WalkDemo(movement, world.clock)))
    yield
    for stop in reversed(stops):
        stop()
