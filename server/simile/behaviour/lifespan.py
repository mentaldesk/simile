from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette


@asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    from simile.behaviour.mind import behaviour_of
    from simile.behaviour.snapshot import snapshot
    from simile.memory import memory_of
    from simile.protocol import hub_of
    from simile.sim import world_of

    behaviour, hub = behaviour_of(app), hub_of(app)
    behaviour.start()
    previous = hub.snapshot
    hub.snapshot = lambda: snapshot(behaviour)
    unregister = world_of(app).loop.register(behaviour)
    unlisten = memory_of(app).listen(behaviour.inspire)
    yield
    unlisten()
    unregister()
    hub.snapshot = previous
