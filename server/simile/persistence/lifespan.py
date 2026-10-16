import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from starlette.applications import Starlette

logger = logging.getLogger(__name__)

FRESH_ENV = "SIMILE_FRESH"
SAVE_EVERY = 10.0
"""Real seconds between saves."""


@asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    from simile.behaviour import behaviour_of
    from simile.memory import memory_of
    from simile.persistence.saver import Saver
    from simile.persistence.state import restore
    from simile.persistence.store import WorldStore

    path = memory_of(app).path
    if path == Path(":memory:"):
        yield
        return
    behaviour = behaviour_of(app)
    with WorldStore(path) as store:
        if os.environ.get(FRESH_ENV) == "1":
            store.clear()
            logger.info("%s  Starting a fresh village in %s", behaviour.clock, path)
        elif (world := store.load()) is not None:
            restore(world, behaviour)
            logger.info("%s  Resumed the village from %s", behaviour.clock, path)
        app.state.persistence = Saver(store, behaviour)
        yield


@asynccontextmanager
async def running(app: Starlette) -> AsyncIterator[None]:
    from simile.persistence.saver import end_conversations

    saver = getattr(app.state, "persistence", None)
    if saver is None:
        yield
        return
    autosave = asyncio.create_task(saver.autosave(SAVE_EVERY))
    try:
        yield
    finally:
        saver.stop()
        await autosave
    clock = saver.behaviour.clock
    if (engine := getattr(app.state, "conversation", None)) is not None:
        await engine.close()
        for conversation in end_conversations(engine):
            logger.info("%s  Ended %s for the shutdown", clock, conversation.id)
    if (reflector := getattr(app.state, "reflection", None)) is not None and reflector.tasks:
        logger.info("%s  Waiting for %d reflections", clock, len(reflector.tasks))
        await asyncio.gather(*reflector.tasks, return_exceptions=True)
    await saver.save()
    logger.info("%s  Saved the village to %s", clock, saver.store.path)
