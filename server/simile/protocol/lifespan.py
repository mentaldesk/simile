from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime

from starlette.applications import Starlette

from simile.protocol.hub import Hub, hub_of
from simile.protocol.messages import (
    ClockMessage,
    ConversationEndedMessage,
    ConversationStartedMessage,
    EntityMovedMessage,
    LineMessage,
    Position,
    ServerMessage,
)
from simile.schema import Line
from simile.sim import (
    Clock,
    ConversationEnded,
    ConversationStarted,
    EntityMoved,
    Event,
    LineSpoken,
    world_of,
)

FORWARDED = (EntityMoved, ConversationStarted, LineSpoken, ConversationEnded)


def unvoiced(line: Line) -> bool:
    return False


def message_for(
    event: Event, now: datetime, voiced: Callable[[Line], bool] = unvoiced
) -> ServerMessage:
    match event:
        case EntityMoved():
            return EntityMovedMessage(
                entity_id=event.entity, position=Position(x=event.x, y=event.y)
            )
        case ConversationStarted():
            return ConversationStartedMessage(conversation=event.conversation)
        case LineSpoken():
            return LineMessage(line=event.line, voiced=voiced(event.line))
        case ConversationEnded():
            return ConversationEndedMessage(
                conversation_id=event.conversation.id, ended=event.conversation.ended or now
            )
    raise TypeError(f"no message for {event!r}")


class ClockSync:
    def __init__(self, clock: Clock, hub: Hub) -> None:
        self.clock = clock
        self.hub = hub
        self.sent = self.reading()

    def reading(self) -> tuple[datetime, float]:
        return self.clock.now.replace(second=0, microsecond=0), self.clock.speed

    def message(self) -> ClockMessage:
        return ClockMessage(time=self.clock.now, speed=self.clock.speed)

    def tick(self, dt: float) -> None:
        if (reading := self.reading()) != self.sent:
            self.sent = reading
            self.hub.broadcast(self.message())


@asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    world, hub = world_of(app), hub_of(app)

    def forward(event: Event) -> None:
        voiced = getattr(app.state, "voiced", unvoiced)
        hub.broadcast(message_for(event, world.clock.now, voiced))

    unsubscribes = [world.bus.subscribe(event_type, forward) for event_type in FORWARDED]
    sync = ClockSync(world.clock, hub)
    unsubscribes.append(world.loop.register(sync))
    hub.clock = sync.message
    yield
    hub.clock = None
    for unsubscribe in unsubscribes:
        unsubscribe()
