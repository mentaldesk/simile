from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette


@asynccontextmanager
async def running(app: Starlette) -> AsyncIterator[None]:
    from simile.sim import world_of
    from simile.theft.theft import theft_of

    unregister = world_of(app).loop.register(theft_of(app))
    yield
    unregister()
