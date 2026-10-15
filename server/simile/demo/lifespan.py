import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette

from simile.demo.walkers import Demo
from simile.protocol import hub_of
from simile.sim import world_of
from simile.world.map import load_map

logger = logging.getLogger(__name__)

ENV = "SIMILE_DEMO"


def enabled(app: Starlette) -> bool:
    return os.environ.get(ENV) == "1" and not getattr(app.state, "headless", False)


@asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    if not enabled(app):
        yield
        return
    world, hub = world_of(app), hub_of(app)
    fixtures = hub.snapshot
    demo = Demo(load_map(), fixtures().entities, world.bus.publish)
    hub.snapshot = lambda: demo.snapshot(fixtures())
    unregister = world.loop.register(demo)
    logger.info("Demo mode: %d NPCs walk errands in a loop", len(demo.walkers))
    try:
        yield
    finally:
        unregister()
        hub.snapshot = fixtures
