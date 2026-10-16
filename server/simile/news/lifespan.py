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
    from simile.llm import LLMClient
    from simile.memory import memory_of
    from simile.news.analysis import NewsAnalyser
    from simile.news.reactions import NewsReader

    def llm() -> LLMClient | None:
        return getattr(app.state, "llm", None)

    world = world_of(app)
    async with AsyncExitStack() as stack:
        store = stack.enter_context(news_of(app))

        reader = NewsReader(store, memory_of(app), world.clock, llm)
        stack.push_async_callback(reader.stop)
        stack.callback(
            behaviour_of(app).hooks.set(read_news=reader.read, news_interest=reader.interest)
        )
        analyser = NewsAnalyser(store, llm)
        stack.push_async_callback(analyser.stop)
        stack.callback(world.loop.register(analyser))
        if os.environ.get("SIMILE_NEWS") == "1":
            refresher = NewsRefresher(store)
            stack.push_async_callback(refresher.stop)
            stack.callback(world.loop.register(refresher))
        yield
