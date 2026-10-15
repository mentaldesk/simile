from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette


@asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    from simile.behaviour import behaviour_of
    from simile.memory import memory_of
    from simile.reflection.reflector import Reflector
    from simile.sim import ConversationEnded, world_of

    reflector = Reflector(
        memory_of(app),
        lambda: behaviour_of(app).npcs,
        lambda: getattr(app.state, "llm", None),
    )
    app.state.reflection = reflector
    unsubscribe = world_of(app).bus.subscribe(ConversationEnded, reflector.on_ended)
    try:
        yield
    finally:
        unsubscribe()
        await reflector.stop()
