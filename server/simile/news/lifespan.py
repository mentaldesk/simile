import os
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from starlette.applications import Starlette

from simile.news.refresh import NewsRefresher
from simile.news.store import news_of
from simile.sim import world_of


@asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    from simile.behaviour import behaviour_of
    from simile.memory import memory_of
    from simile.news.reactions import NewsReader

    world = world_of(app)
    async with AsyncExitStack() as stack:
        store = stack.enter_context(news_of(app))
        reader = NewsReader(
            store, memory_of(app), world.clock, lambda: getattr(app.state, "llm", None)
        )
        stack.push_async_callback(reader.stop)
        stack.callback(behaviour_of(app).hooks.set(read_news=reader.read))
        if os.environ.get("SIMILE_NEWS") == "1":
            refresher = NewsRefresher(store)
            stack.push_async_callback(refresher.stop)
            stack.callback(world.loop.register(refresher))
        yield
