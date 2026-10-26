import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette


@asynccontextmanager
async def running(app: Starlette) -> AsyncIterator[None]:
    """Under the supervisor, records the world as the last played once it's up, so a world that
    won't start isn't opened again."""
    from simile.worlds.store import running as running_id
    from simile.worlds.store import worlds_of
    from simile.worlds.supervisor import SUPERVISOR_ENV

    worlds = worlds_of(app)
    id = running_id(worlds.root) if os.environ.get(SUPERVISOR_ENV) else None
    if id is not None:
        worlds.index.opened(id)
    try:
        yield
    finally:
        if id is not None:
            worlds.index.closed(id)
