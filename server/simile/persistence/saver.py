import asyncio
import logging

from simile.behaviour import Behaviour
from simile.conversation import ConversationEngine
from simile.persistence.config import DEFAULT_CONFIG, PersistenceConfig
from simile.persistence.state import SavedWorld, capture
from simile.persistence.store import WorldStore
from simile.reflection import Reflector

logger = logging.getLogger(__name__)


class Saver:
    """Saves the world to a `WorldStore` when asked, and every so often until stopped. The
    snapshot is taken between ticks and written on a thread, so the tick never waits."""

    def __init__(
        self, store: WorldStore, behaviour: Behaviour, config: PersistenceConfig = DEFAULT_CONFIG
    ) -> None:
        self.store = store
        self.behaviour = behaviour
        self.config = config
        self._stopping = asyncio.Event()

    async def save(self) -> SavedWorld:
        world = capture(self.behaviour)
        await asyncio.to_thread(self.store.save, world)
        return world

    async def autosave(self) -> None:
        """Save every `save_every` real seconds until `stop`, finishing any save under way."""
        while True:
            try:
                await asyncio.wait_for(self._stopping.wait(), self.config.save_every)
                return
            except TimeoutError:
                pass
            try:
                await self.save()
            except Exception:
                logger.exception("Couldn't save the world to %s", self.store.path)

    def stop(self) -> None:
        self._stopping.set()

    async def shut_down(
        self, engine: ConversationEngine | None, reflector: Reflector | None
    ) -> None:
        """End the conversations going on, so B3 reflects on them, give every reflection under
        way up to `reflection_wait` to finish, and save."""
        clock = self.behaviour.clock
        if engine is not None:
            for conversation in engine.live():
                engine.end(conversation.id)
                logger.info("%s  Ended %s for the shutdown", clock, conversation.id)
        if reflector and reflector.tasks:
            wait = self.config.reflection_wait
            logger.info(
                "%s  Waiting up to %gs for %d reflections", clock, wait, len(reflector.tasks)
            )
            _, pending = await asyncio.wait(list(reflector.tasks), timeout=wait)
            if pending:
                logger.warning("%s  Gave up on %d reflections, which are lost", clock, len(pending))
        await self.save()
        logger.info("%s  Saved the village to %s", clock, self.store.path)
