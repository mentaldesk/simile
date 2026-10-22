import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from starlette.applications import Starlette

logger = logging.getLogger(__name__)

FRESH_ENV = "SIMILE_FRESH"


@asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    from simile.behaviour import behaviour_of
    from simile.memory import memory_of
    from simile.persistence.saver import Saver
    from simile.persistence.state import investigation_of, player_of, restore
    from simile.persistence.store import WorldStore

    memory = memory_of(app)
    if memory.path == Path(":memory:"):
        yield
        return
    behaviour = behaviour_of(app)
    economy = getattr(app.state, "economy", None)
    with WorldStore(memory) as store:
        if os.environ.get(FRESH_ENV) == "1":
            store.clear()
            logger.info("%s  Starting a fresh village in %s", behaviour.clock, store.path)
        elif (world := store.load()) is not None:
            restore(world, behaviour, economy, player_of(app), investigation_of(app))
            logger.info("%s  Resumed the village from %s", behaviour.clock, store.path)
        app.state.persistence = Saver(
            store,
            behaviour,
            economy=economy,
            player=lambda: player_of(app),
            investigation=lambda: investigation_of(app),
        )
        yield


@asynccontextmanager
async def running(app: Starlette) -> AsyncIterator[None]:
    saver = getattr(app.state, "persistence", None)
    if saver is None:
        yield
        return
    autosave = asyncio.create_task(saver.autosave())
    try:
        yield
    finally:
        saver.stop()
        await autosave
    await saver.shut_down(
        getattr(app.state, "conversation", None), getattr(app.state, "reflection", None)
    )
