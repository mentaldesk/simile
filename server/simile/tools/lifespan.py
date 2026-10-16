import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from starlette.applications import Starlette

logger = logging.getLogger(__name__)

RECORD_ENV = "SIMILE_RECORD"


@asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    try:
        yield
    finally:
        if (recorder := getattr(app.state, "recorder", None)) is not None:
            recorder.finish()
            recorder.store.close()


@asynccontextmanager
async def running(app: Starlette) -> AsyncIterator[None]:
    if os.environ.get(RECORD_ENV) == "1":
        record(app)
    yield


def record(app: Starlette) -> None:
    """Start recording the run. The lifespan finishes it once every module's `running` has
    stopped, so it includes the conversations ended and reflected on at shutdown."""
    from simile.behaviour import behaviour_of
    from simile.memory import memory_of
    from simile.sim import world_of
    from simile.tools.recorder import Recorder, RecordStore

    memory = memory_of(app)
    if memory.path == Path(":memory:"):
        logger.warning("%s=1 but the database is in memory, so nothing is recorded", RECORD_ENV)
        return
    world = world_of(app)
    recorder = Recorder(
        RecordStore(memory.path),
        world,
        behaviour_of(app),
        memory,
        getattr(app.state, "llm", None),
    )
    run = recorder.start()
    app.state.recorder = recorder
    logger.info("%s  Recording run %d to %s for `simile report`", world.clock, run, memory.path)
