from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette


@asynccontextmanager
async def running(app: Starlette) -> AsyncIterator[None]:
    from simile.machines.workshop import Workshop, register_offers
    from simile.persistence import player_of
    from simile.protocol import MachineChangedMessage, MakeMessage, RepairMessage, hub_of
    from simile.sim import world_of
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
    stops = [
        world_of(app).loop.register(workshop),
        hub.subscribe(RepairMessage, lambda message: workshop.repair(message.machine)),
        hub.subscribe(MakeMessage, lambda message: workshop.make(message.machine, message.item)),
    ]
    try:
        yield
    finally:
        for stop in reversed(stops):
            stop()
        hub.snapshot = snapshot
        del app.state.workshop
