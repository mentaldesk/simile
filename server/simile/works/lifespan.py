from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from starlette.applications import Starlette

from simile.sim import world_of
from simile.works.store import works_of


@asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    from simile.behaviour import Activity, behaviour_of
    from simile.llm import LLMClient
    from simile.memory import memory_of
    from simile.protocol import ListWorksMessage, ReadWorkMessage, hub_of
    from simile.schema import Id
    from simile.works.maker import Maker
    from simile.works.player import PlayerWorks
    from simile.works.reading import WorksReader
    from simile.works.sightings import Passers
    from simile.works.walls import Walls

    def llm() -> LLMClient | None:
        return getattr(app.state, "llm", None)

    world, memory, behaviour, hub = world_of(app), memory_of(app), behaviour_of(app), hub_of(app)
    hooks, town, npcs = behaviour.hooks, behaviour.movement.town, behaviour.npcs

    def painting() -> dict[Id, Id]:
        return {
            who: mind.goal.target
            for who, mind in behaviour.minds.items()
            if mind.goal.activity is Activity.CREATE and mind.goal.target
        }

    async with AsyncExitStack() as stack:
        store = stack.enter_context(works_of(app))
        walls = Walls(
            town.murals,
            store,
            memory,
            world.clock,
            npcs,
            positions=behaviour.movement.entities,
            painting=painting,
        )
        app.state.maker = maker = Maker(
            store,
            memory,
            world.clock,
            llm,
            walls=town.murals,
            npcs=npcs,
            painted=lambda _: hub.broadcast(walls.message()),
        )
        stack.push_async_callback(maker.stop)
        reader = WorksReader(
            store,
            memory,
            world.clock,
            llm,
            npcs,
            news_interest=hooks.news_interest,
            read_news=hooks.read_news,
        )
        stack.push_async_callback(reader.stop)
        stack.callback(
            hooks.set(
                create=maker.make,
                mural_wall=walls.pick,
                news_interest=reader.interest,
                read_news=reader.read,
            )
        )
        passers = Passers(
            store, memory, world.clock, llm, npcs, town.murals, behaviour.movement.entities
        )
        stack.push_async_callback(passers.stop)
        stack.callback(world.loop.register(passers))
        stack.callback(hub.greet(walls.greeting))
        player = PlayerWorks(store, memory, world.clock, npcs)
        stack.callback(hub.subscribe(ListWorksMessage, lambda _: hub.broadcast(player.listing())))
        stack.callback(
            hub.subscribe(
                ReadWorkMessage, lambda message: hub.broadcast(player.read(message.work_id))
            )
        )
        yield
