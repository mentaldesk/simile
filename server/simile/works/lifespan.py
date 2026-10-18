import logging
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

from starlette.applications import Starlette

from simile.sim import world_of
from simile.works.store import works_of

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    from simile.behaviour import Activity, behaviour_of
    from simile.llm import LLMClient
    from simile.memory import memory_of
    from simile.protocol import ListWorksMessage, ReadWorkMessage, hub_of
    from simile.schema import Id, IntentionKind
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

    def promised(npc: Id) -> Id | None:
        return next(
            (
                intention.target
                for intention in behaviour.intentions(npc)
                if intention.kind is IntentionKind.CREATE and intention.target
            ),
            None,
        )

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
            promised=promised,
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
        stack.callback(hub.greet(walls.message))
        player = PlayerWorks(store, memory, world.clock, npcs)
        stack.callback(hub.subscribe(ListWorksMessage, lambda _: hub.broadcast(player.listing())))
        stack.callback(
            hub.subscribe(
                ReadWorkMessage, lambda message: hub.broadcast(player.read(message.work_id))
            )
        )
        yield


@asynccontextmanager
async def running(app: Starlette) -> AsyncIterator[None]:
    """A fresh save of today's village starts with the works it ships with, and a new world's
    starts making its own in the background. Never into an in-memory store."""
    from simile.behaviour import behaviour_of
    from simile.casting import load_cast
    from simile.memory import memory_of
    from simile.works.starters import commission, seed

    memory = memory_of(app)
    if memory.path != Path(":memory:"):
        behaviour, works, clock = behaviour_of(app), works_of(app), world_of(app).clock
        if load_cast() is None:
            gallery = getattr(app.state, "gallery", None)
            hang = gallery.hang if gallery is not None else None
            if seeded := seed(works, memory, behaviour.npcs, clock.now, hang=hang):
                logger.info("%s  Seeded today's village with %d starter works", clock, len(seeded))
        else:
            npcs, walls = list(behaviour.npcs.values()), behaviour.movement.town.murals
            if tasks := commission(app.state.maker, works, npcs, walls, clock.now):
                logger.info("%s  Making %d starter works for the new world", clock, len(tasks))
    yield
