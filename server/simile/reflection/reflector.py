import asyncio
import logging
from collections.abc import Callable, Mapping

from simile.llm import LLMClient, LLMError, StructuredOutputError
from simile.memory import MemoryStore
from simile.reflection.config import DEFAULT_CONFIG, ReflectionConfig
from simile.reflection.extraction import SYSTEM, Extraction, gather, prompt
from simile.reflection.outcome import Outcome, outcome
from simile.schema import Conversation, Id, Npc, Relationship
from simile.sim import ConversationEnded

logger = logging.getLogger(__name__)


class Reflector:
    """Hears every `ConversationEnded` and, in a task, asks the LLM what it meant to each NPC in
    it, then stores their memories, the events, the flags and how they now feel."""

    def __init__(
        self,
        memory: MemoryStore,
        npcs: Callable[[], Mapping[Id, Npc]],
        llm: Callable[[], LLMClient | None],
        *,
        config: ReflectionConfig = DEFAULT_CONFIG,
    ) -> None:
        self.memory = memory
        self.npcs = npcs
        self.llm = llm
        self.config = config
        self.tasks: set[asyncio.Task[Outcome | None]] = set()

    def on_ended(self, event: ConversationEnded) -> None:
        """Start reflecting on the conversation. Doesn't block."""
        conversation = event.conversation
        if not conversation.lines:
            return
        llm = self.llm()
        if llm is None:
            return
        task = asyncio.get_running_loop().create_task(self.reflect(llm, conversation))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def reflect(self, llm: LLMClient, conversation: Conversation) -> Outcome | None:
        try:
            return await self._reflect(llm, conversation)
        except Exception:
            logger.exception("Couldn't reflect on %s", conversation.id)
            return None

    async def stop(self) -> None:
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _reflect(self, llm: LLMClient, conversation: Conversation) -> Outcome | None:
        context = gather(conversation, self.npcs(), self.memory, self.config)
        if not context.npcs:
            return None
        try:
            extraction = await llm.structured(
                prompt(context, self.config),
                Extraction,
                system=SYSTEM,
                model=self.config.model,
                purpose="reflection",
                priority=self.config.priority,
            )
        except StructuredOutputError:
            logger.warning("Couldn't make sense of %s, so skipped it", conversation.id)
            return None
        except LLMError as error:
            logger.warning("Couldn't reflect on %s: %s", conversation.id, error)
            return None
        result = outcome(context, extraction, self.memory, self.config)
        self.memory.add(*result.records)
        for key, after in result.after.items():
            logger.info("%s: %s", conversation.id, change(result.before[key], after))
        return result


def change(before: Relationship, after: Relationship) -> str:
    scores = ", ".join(
        f"{aspect} {getattr(before, aspect):.2f}->{getattr(after, aspect):.2f}"
        for aspect in ("like", "trust", "respect", "familiarity")
    )
    was = {flag.id: flag for flag in before.flags}
    flags = [
        f"{'+' if flag.id not in was else '-'}{flag.kind.value} ({flag.description})"
        for flag in after.flags
        if flag.id not in was or (flag.resolved and not was[flag.id].resolved)
    ]
    return f"{after.owner} about {after.about}: {scores}" + "".join(f", {f}" for f in flags)
