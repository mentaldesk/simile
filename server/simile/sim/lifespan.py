import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette

from simile.sim.world import world_of

logger = logging.getLogger(__name__)


def log_crash(task: asyncio.Task[None]) -> None:
    if not task.cancelled() and (error := task.exception()):
        logger.error("The tick loop stopped", exc_info=error)


@asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    world = world_of(app)
    if getattr(app.state, "headless", False):
        yield
        return
    task = asyncio.create_task(world.loop.run())
    task.add_done_callback(log_crash)
    try:
        yield
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
