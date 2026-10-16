import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette


@asynccontextmanager
async def running(app: Starlette) -> AsyncIterator[None]:
    if getattr(app.state, "headless", False):
        yield
        return
    from simile.behaviour import behaviour_of
    from simile.conversation import conversations_of
    from simile.debug.overlay import INTERVAL, Overlay
    from simile.debug.state import Village
    from simile.memory import memory_of
    from simile.protocol import WatchNpcMessage, hub_of

    village = Village(behaviour_of(app), conversations_of(app), memory_of(app))
    hub = hub_of(app)
    overlay = app.state.debug = Overlay(hub.broadcast, village.npc_state)
    unsubscribe = hub.subscribe(WatchNpcMessage, overlay.watch)
    task = asyncio.create_task(overlay.run(INTERVAL))
    try:
        yield
    finally:
        unsubscribe()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
