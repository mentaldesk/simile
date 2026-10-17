from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from starlette.applications import Starlette

from simile.sim import world_of
from simile.works.store import works_of


@asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    from simile.llm import LLMClient
    from simile.memory import memory_of
    from simile.works.maker import Maker

    def llm() -> LLMClient | None:
        return getattr(app.state, "llm", None)

    async with AsyncExitStack() as stack:
        store = stack.enter_context(works_of(app))
        app.state.maker = maker = Maker(store, memory_of(app), world_of(app).clock, llm)
        stack.push_async_callback(maker.stop)
        yield
