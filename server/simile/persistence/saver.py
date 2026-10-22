import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from simile.behaviour import Behaviour
from simile.conversation import ConversationEngine
from simile.persistence.config import DEFAULT_CONFIG, PersistenceConfig
from simile.persistence.state import SavedWorld, capture
from simile.persistence.store import WorldStore
from simile.reflection import Reflector
from simile.schema import Player

if TYPE_CHECKING:
    from simile.economy.economy import Economy

logger = logging.getLogger(__name__)


class Saver:
    """Saves the world to a `WorldStore` when asked, and every so often until stopped. The
    snapshot is taken between ticks and written on a thread, so the tick never waits."""

    def __init__(
        self,
        store: WorldStore,
        behaviour: Behaviour,
        config: PersistenceConfig = DEFAULT_CONFIG,
        *,
        economy: "Economy | None" = None,
        player: Callable[[], Player] = Player,
    ) -> None:
        self.store = store
        self.behaviour = behaviour
        self.config = config
        self.economy = economy
        self.player = player
        """The player as they are now, looked up at each save."""
        self._stopping = asyncio.Event()
        self._ledgered = 0
        """How many of the ledger's entries are saved."""

    async def save(self) -> SavedWorld:
        world = capture(self.behaviour, self.economy, self.player())
        entries = self.economy.ledger.entries[self._ledgered :] if self.economy else []
        await asyncio.to_thread(self.store.save, world, entries)
        self._ledgered += len(entries)
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
