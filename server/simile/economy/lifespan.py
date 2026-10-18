from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette


@asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    from simile.cafe.events import Served
    from simile.economy.economy import economy_of
    from simile.sim import world_of

    world, economy = world_of(app), economy_of(app)
    unplug = economy.behaviour.hooks.set(
        money=economy.money_of,
        price=economy.price,
        earnings=economy.earnings,
        supply=economy.supply,
    )
    unsubscribe = world.bus.subscribe(Served, economy.on_served)
    unregister = world.loop.register(economy)
    yield
    unregister()
    unsubscribe()
    unplug()
