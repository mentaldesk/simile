from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette


@asynccontextmanager
async def running(app: Starlette) -> AsyncIterator[None]:
    from simile.combat.shooting import Shooting
    from simile.creatures.engine import creatures_of
    from simile.persistence import player_of
    from simile.protocol import FireMessage, ReloadMessage, hub_of
    from simile.sim import world_of
    from simile.world import movement_of

    hub = hub_of(app)
    shooting = Shooting(player_of(app), movement_of(app), creatures_of(app), world_of(app).clock)
    stops = [
        hub.subscribe(FireMessage, lambda message: shooting.fire(message.facing)),
        hub.subscribe(ReloadMessage, lambda message: shooting.reload()),
    ]
    yield
    for stop in reversed(stops):
        stop()
