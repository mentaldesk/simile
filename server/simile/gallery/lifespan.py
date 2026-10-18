from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from starlette.applications import Starlette


@asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    from simile.behaviour import behaviour_of
    from simile.gallery.gallery import Gallery, frames_of
    from simile.gallery.store import gallery_store_of
    from simile.protocol import hub_of
    from simile.sim import world_of
    from simile.works.store import works_of

    behaviour, hub = behaviour_of(app), hub_of(app)
    with gallery_store_of(app) as store:
        app.state.gallery = gallery = Gallery(
            frames_of(behaviour.movement.maps),
            store,
            works_of(app),
            world_of(app).clock,
            behaviour.npcs,
            hung=lambda: hub.broadcast(gallery.message()),
        )
        stop_greeting = hub.greet(gallery.message)
        try:
            yield
        finally:
            stop_greeting()


@asynccontextmanager
async def running(app: Starlette) -> AsyncIterator[None]:
    """Visitors are shown round, and once works is up, muralists take turns painting for the
    gallery and paintings hang. Stops before any module shuts down."""
    from simile.behaviour import GoalChosen, behaviour_of
    from simile.gallery.gallery import taking_turns
    from simile.gallery.visits import Visitors
    from simile.llm import LLMClient
    from simile.memory import memory_of
    from simile.sim import world_of
    from simile.works.store import works_of

    def llm() -> LLMClient | None:
        return getattr(app.state, "llm", None)

    world, behaviour, gallery = world_of(app), behaviour_of(app), app.state.gallery
    maker = getattr(app.state, "maker", None)
    async with AsyncExitStack() as stack:
        visitors = Visitors(
            gallery,
            memory_of(app),
            world.clock,
            llm,
            behaviour.npcs,
            behaviour.minds,
            behaviour.movement,
        )
        stack.push_async_callback(visitors.stop)
        stack.callback(world.loop.register(visitors))
        stack.callback(world.bus.subscribe(GoalChosen, visitors.on_goal))
        if maker is not None:
            hooks = behaviour.hooks
            turns = taking_turns(hooks.mural_wall, works_of(app), behaviour.places)
            stack.callback(hooks.set(mural_wall=turns))
            maker.hang = gallery.hang
            stack.callback(setattr, maker, "hang", None)
        yield
