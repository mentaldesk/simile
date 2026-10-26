from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette


@asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    from simile.story.begin import begin

    await begin(app)
    yield


@asynccontextmanager
async def running(app: Starlette) -> AsyncIterator[None]:
    from simile.story.lens import give
    from simile.story.recording import record

    stops = [record(app), give(app)]
    yield
    for stop in reversed(stops):
        stop()
