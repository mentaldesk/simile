from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette


@asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    from simile.jobs.runner import jobs_of
    from simile.jobs.sprite import SPRITE

    jobs = jobs_of(app)
    unregister = jobs.register(SPRITE)
    try:
        yield
    finally:
        await jobs.close()
        unregister()
