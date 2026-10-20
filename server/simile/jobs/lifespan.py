from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette


@asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    from simile.dolls.job import DOLL
    from simile.jobs.runner import jobs_of

    jobs = jobs_of(app)
    jobs.remove_leftovers()
    unregister = jobs.register(DOLL)
    try:
        yield
    finally:
        await jobs.close()
        unregister()
