from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette


@asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    from simile.behaviour import behaviour_of
    from simile.conversation.loans import Loan
    from simile.memory import memory_of
    from simile.reflection.reflector import Reflector
    from simile.sim import ConversationEnded, world_of

    def settle(conversation_id: str) -> Loan | None:
        engine = getattr(app.state, "conversation", None)
        return engine.settle(conversation_id) if engine is not None else None

    reflector = Reflector(
        memory_of(app),
        lambda: behaviour_of(app).npcs,
        lambda: getattr(app.state, "llm", None),
        settle=settle,
        economy=lambda: getattr(app.state, "economy", None),
    )
    app.state.reflection = reflector
    unsubscribe = world_of(app).bus.subscribe(ConversationEnded, reflector.on_ended)
    try:
        yield
    finally:
        unsubscribe()
        await reflector.stop()
