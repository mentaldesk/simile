import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette

from simile.news.refresh import NewsRefresher
from simile.news.store import news_of
from simile.sim import world_of


@asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    with news_of(app) as store:
        if os.environ.get("SIMILE_NEWS") != "1":
            yield
            return
        refresher = NewsRefresher(store)
        unregister = world_of(app).loop.register(refresher)
        try:
            yield
        finally:
            unregister()
            await refresher.stop()
