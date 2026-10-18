import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette

logger = logging.getLogger(__name__)


@asynccontextmanager
async def running(app: Starlette) -> AsyncIterator[None]:
    from simile.casting.history import history, seeded
    from simile.casting.store import load_cast
    from simile.memory import memory_of
    from simile.sim import world_of

    if (cast := load_cast()) is not None:
        memory, clock = memory_of(app), world_of(app).clock
        residents = [resident.character.id for resident in cast.residents]
        if not seeded(memory, residents, clock.now):
            records = history(cast, clock.now)
            memory.add(*records)
            logger.info("%s  Seeded the cast's history: %d records", clock, len(records))
    yield
