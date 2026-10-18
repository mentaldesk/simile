from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette


@asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    from simile.behaviour import IntentionBroken, IntentionKept, Options, behaviour_of
    from simile.conversation.loans import Loan
    from simile.memory import memory_of
    from simile.reflection.reflector import Reflector
    from simile.schema import Id, Intention
    from simile.sim import ConversationEnded, world_of

    def settle(conversation_id: str) -> Loan | None:
        engine = getattr(app.state, "conversation", None)
        return engine.settle(conversation_id) if engine is not None else None

    def options(npc: Id) -> Options | None:
        behaviour = behaviour_of(app)
        return behaviour.options(npc) if npc in behaviour.minds else None

    def planned(npc: Id) -> list[Intention]:
        return behaviour_of(app).intentions(npc)

    def intend(intention: Intention) -> bool:
        return behaviour_of(app).intend(intention)

    world = world_of(app)
    reflector = Reflector(
        memory_of(app),
        lambda: behaviour_of(app).npcs,
        lambda: getattr(app.state, "llm", None),
        settle=settle,
        economy=lambda: getattr(app.state, "economy", None),
        options=options,
        planned=planned,
        intend=intend,
        clock=world.clock,
    )
    app.state.reflection = reflector
    stops = [
        world.bus.subscribe(ConversationEnded, reflector.on_ended),
        world.bus.subscribe(IntentionBroken, reflector.on_broken),
        world.bus.subscribe(IntentionKept, reflector.on_kept),
    ]
    try:
        yield
    finally:
        for stop in stops:
            stop()
        await reflector.stop()
