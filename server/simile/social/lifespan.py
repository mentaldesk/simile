from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette


@asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    from simile.behaviour import behaviour_of
    from simile.sim import world_of
    from simile.social.sightings import sightings_of

    sightings = sightings_of(app)
    stops = [
        world_of(app).loop.register(sightings),
        behaviour_of(app).hooks.set(unease=sightings.unease),
    ]
    yield
    for stop in reversed(stops):
        stop()
