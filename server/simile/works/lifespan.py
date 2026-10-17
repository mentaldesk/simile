from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from starlette.applications import Starlette

from simile.sim import world_of
from simile.works.store import works_of


@asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    from simile.behaviour import behaviour_of
    from simile.llm import LLMClient
    from simile.memory import memory_of
    from simile.protocol import ListWorksMessage, ReadWorkMessage, hub_of
    from simile.works.maker import Maker
    from simile.works.player import PlayerWorks
    from simile.works.reading import WorksReader

    def llm() -> LLMClient | None:
        return getattr(app.state, "llm", None)

    world, memory, behaviour = world_of(app), memory_of(app), behaviour_of(app)
    hooks = behaviour.hooks
    async with AsyncExitStack() as stack:
        store = stack.enter_context(works_of(app))
        app.state.maker = maker = Maker(store, memory, world.clock, llm)
        stack.push_async_callback(maker.stop)
        reader = WorksReader(
            store,
            memory,
            world.clock,
            llm,
            behaviour.npcs,
            news_interest=hooks.news_interest,
            read_news=hooks.read_news,
        )
        stack.push_async_callback(reader.stop)
        stack.callback(
            hooks.set(
                create=lambda npc, _: maker.make(npc),
                news_interest=reader.interest,
                read_news=reader.read,
            )
        )
        player, hub = PlayerWorks(store, memory, world.clock, behaviour.npcs), hub_of(app)
        stack.callback(hub.subscribe(ListWorksMessage, lambda _: hub.broadcast(player.listing())))
        stack.callback(
            hub.subscribe(
                ReadWorkMessage, lambda message: hub.broadcast(player.read(message.work_id))
            )
        )
        yield
