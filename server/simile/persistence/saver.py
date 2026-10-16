import asyncio
import logging
from datetime import timedelta

from simile.behaviour import Behaviour
from simile.conversation import ConversationEngine
from simile.persistence.state import SavedWorld, capture
from simile.persistence.store import WorldStore
from simile.schema import Conversation
from simile.sim import ConversationEnded

logger = logging.getLogger(__name__)


class Saver:
    """Saves the world to a `WorldStore` when asked, and every so often until stopped. The
    snapshot is taken between ticks and written on a thread, so the tick never waits."""

    def __init__(self, store: WorldStore, behaviour: Behaviour) -> None:
        self.store = store
        self.behaviour = behaviour
        self._stopping = asyncio.Event()

    async def save(self) -> SavedWorld:
        world = capture(self.behaviour)
        await asyncio.to_thread(self.store.save, world)
        return world

    async def autosave(self, every: float) -> None:
        """Save every `every` real seconds until `stop`, finishing any save under way."""
        while True:
            try:
                await asyncio.wait_for(self._stopping.wait(), every)
                return
            except TimeoutError:
                pass
            try:
                await self.save()
            except Exception:
                logger.exception("Couldn't save the world to %s", self.store.path)

    def stop(self) -> None:
        self._stopping.set()


def end_conversations(engine: ConversationEngine) -> list[Conversation]:
    """End every live conversation now, as the engine does when one runs out: both NPCs resume
    and leave each other be for the cooldown, and `ConversationEnded` is published."""
    behaviour, now = engine.behaviour, engine.clock.now
    cooldown = now + timedelta(minutes=engine.config.cooldown)
    ended = engine.live()
    for conversation in ended:
        conversation.ended = now
        for npc in conversation.participants:
            if (mind := behaviour.minds.get(npc)) is not None:
                mind.cooldowns.update(
                    {other: cooldown for other in conversation.participants if other != npc}
                )
            behaviour.resume(npc)
        engine.bus.publish(ConversationEnded(conversation))
    return ended
