from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime

from starlette.applications import Starlette

from simile.protocol.hub import hub_of
from simile.protocol.messages import (
    ConversationEndedMessage,
    ConversationStartedMessage,
    EntityMovedMessage,
    LineMessage,
    Position,
    ServerMessage,
)
from simile.sim import (
    ConversationEnded,
    ConversationStarted,
    EntityMoved,
    Event,
    LineSpoken,
    world_of,
)

FORWARDED = (EntityMoved, ConversationStarted, LineSpoken, ConversationEnded)


def message_for(event: Event, now: datetime) -> ServerMessage:
    match event:
        case EntityMoved():
            return EntityMovedMessage(
                entity_id=event.entity, position=Position(x=event.x, y=event.y)
            )
        case ConversationStarted():
            return ConversationStartedMessage(conversation=event.conversation)
        case LineSpoken():
            return LineMessage(line=event.line, voiced=False)
        case ConversationEnded():
            return ConversationEndedMessage(
                conversation_id=event.conversation.id, ended=event.conversation.ended or now
            )
    raise TypeError(f"no message for {event!r}")


@asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    world, hub = world_of(app), hub_of(app)

    def forward(event: Event) -> None:
        hub.broadcast(message_for(event, world.clock.now))

    unsubscribes = [world.bus.subscribe(event_type, forward) for event_type in FORWARDED]
    yield
    for unsubscribe in unsubscribes:
        unsubscribe()
