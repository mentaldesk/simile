from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette


@asynccontextmanager
async def running(app: Starlette) -> AsyncIterator[None]:
    from simile.cafe.cafe import cafe_of
    from simile.sim import world_of

    cafe = cafe_of(app)
    players = getattr(app.state, "players", None)
    unregister = world_of(app).loop.register(cafe)
    if players is not None and cafe.barista is not None:
        players.writers[cafe.barista] = cafe.write
    try:
        yield
    finally:
        if players is not None and cafe.barista is not None:
            players.writers.pop(cafe.barista, None)
        unregister()
