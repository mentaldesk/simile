import asyncio
import logging
from collections.abc import Callable

from pydantic import JsonValue

from simile.protocol import NpcStateMessage, WatchNpcMessage
from simile.schema import Id

logger = logging.getLogger(__name__)

INTERVAL = 0.5
"""Real seconds between updates for the watched NPC."""

type Broadcast = Callable[[NpcStateMessage], None]
type NpcState = Callable[[Id], dict[str, JsonValue] | None]


class Overlay:
    """Sends `npc_state` for the NPC the debug overlay is watching, and nothing otherwise."""

    def __init__(self, broadcast: Broadcast, npc_state: NpcState) -> None:
        self.broadcast = broadcast
        self.npc_state = npc_state
        self.watched: Id | None = None

    def watch(self, message: WatchNpcMessage) -> None:
        self.watched = message.npc_id
        self.send()

    def send(self) -> None:
        if self.watched is None:
            return
        try:
            state = self.npc_state(self.watched)
            if state is None:
                logger.warning("Not watching %s: there's no such NPC", self.watched)
                self.watched = None
                return
            self.broadcast(NpcStateMessage(npc_id=self.watched, state=state))
        except Exception:
            logger.exception("Couldn't send %s's state to the debug overlay", self.watched)

    async def run(self, interval: float) -> None:
        while True:
            await asyncio.sleep(interval)
            self.send()
