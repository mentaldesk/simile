from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette


@asynccontextmanager
async def running(app: Starlette) -> AsyncIterator[None]:
    from simile.ambient.director import director_of
    from simile.sim import ConversationEnded, ConversationStarted, world_of

    director, world = director_of(app), world_of(app)
    stops = [
        world.bus.subscribe(ConversationStarted, director.earshot.on_started),
        world.bus.subscribe(ConversationEnded, director.earshot.on_ended),
        world.loop.register(director),
    ]
    try:
        yield
    finally:
        for stop in reversed(stops):
            stop()
