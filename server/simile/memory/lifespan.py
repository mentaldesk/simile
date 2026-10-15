from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette

from simile.memory.store import memory_of


@asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    store = memory_of(app)
    try:
        yield
    finally:
        store.close()
