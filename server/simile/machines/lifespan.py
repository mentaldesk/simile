from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette


@asynccontextmanager
async def running(app: Starlette) -> AsyncIterator[None]:
    from simile.machines.workshop import Workshop, register_offers
    from simile.persistence import player_of
    from simile.protocol import MachineChangedMessage, hub_of
    from simile.world import movement_of

    hub = hub_of(app)
    workshop = app.state.workshop = Workshop(
        player_of(app),
        movement_of(app),
        changed=lambda machine: hub.broadcast(MachineChangedMessage(machine=machine)),
    )
    register_offers(workshop)
    snapshot = hub.snapshot
    hub.snapshot = lambda: snapshot().model_copy(update={"machines": workshop.machines()})
    try:
        yield
    finally:
        hub.snapshot = snapshot
        del app.state.workshop
