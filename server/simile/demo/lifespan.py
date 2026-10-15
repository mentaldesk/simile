import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette

logger = logging.getLogger(__name__)

ENV = "SIMILE_DEMO"


def enabled(app: Starlette) -> bool:
    return os.environ.get(ENV) == "1" and not getattr(app.state, "headless", False)


@asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    if not enabled(app):
        yield
        return
    from simile.demo.errands import Errands
    from simile.protocol import hub_of
    from simile.sim import world_of
    from simile.world import movement_of

    world, hub = world_of(app), hub_of(app)
    fixtures = hub.snapshot
    errands = Errands(movement_of(app), fixtures().entities)
    hub.snapshot = lambda: errands.snapshot(fixtures())
    unregister = world.loop.register(errands)
    logger.info("Demo mode: %d NPCs walk errands in a loop", len(errands.walkers))
    try:
        yield
    finally:
        unregister()
        hub.snapshot = fixtures
