import asyncio
import logging
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING

from simile.conversation.loans import Loan
from simile.economy.loans import transfer
from simile.llm import LLMClient, LLMError, StructuredOutputError
from simile.memory import MemoryStore
from simile.reflection.config import DEFAULT_CONFIG, ReflectionConfig
from simile.reflection.extraction import SYSTEM, Context, Extraction, gather, prompt
from simile.reflection.loans import Payment, payment
from simile.reflection.outcome import Outcome, outcome
from simile.schema import Conversation, Id, Npc, Relationship
from simile.sim import ConversationEnded

if TYPE_CHECKING:
    from simile.economy.economy import Economy

logger = logging.getLogger(__name__)


class Reflector:
    """Hears every `ConversationEnded` and, in a task, asks the LLM what it meant to each NPC in
    it, then stores their memories, the events, the flags and how they now feel. Moves the
    money of a loan the conversation was set up to settle (`loans`, by conversation id) through
    the `economy`."""

    def __init__(
        self,
        memory: MemoryStore,
        npcs: Callable[[], Mapping[Id, Npc]],
        llm: Callable[[], LLMClient | None],
        *,
        config: ReflectionConfig = DEFAULT_CONFIG,
        loans: Callable[[str], Loan | None] = lambda _: None,
        economy: "Callable[[], Economy | None]" = lambda: None,
    ) -> None:
        self.memory = memory
        self.npcs = npcs
        self.llm = llm
        self.config = config
        self.loans = loans
        self.economy = economy
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
        paid = self._pay(context, extraction)
        result = outcome(context, extraction, self.memory, self.config, payment=paid)
        self.memory.add(*result.records)
        for key, after in result.after.items():
            logger.info("%s: %s", conversation.id, change(result.before[key], after))
        return result

    def _pay(self, context: Context, extraction: Extraction) -> Payment | None:
        loan, economy = self.loans(context.conversation.id), self.economy()
        if loan is None or economy is None:
            return None
        paid = payment(context, extraction, loan, economy, self.memory)
        if paid is None or not transfer(economy, paid.payer, paid.payee, paid.amount, paid.kind):
            return None
        logger.info(
            "%s: %s paid %s %d (%s)",
            context.conversation.id,
            paid.payer,
            paid.payee,
            paid.amount,
            paid.kind,
        )
        return paid


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
