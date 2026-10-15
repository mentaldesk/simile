from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette


@asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    from simile.behaviour import behaviour_of
    from simile.conversation.engine import conversations_of
    from simile.sim import world_of

    engine = conversations_of(app)
    restore = behaviour_of(app).hooks.set(
        request_conversation=engine.request, conversations=engine.live
    )
    unregister = world_of(app).loop.register(engine)
    try:
        yield
    finally:
        unregister()
        restore()
        await engine.close()
