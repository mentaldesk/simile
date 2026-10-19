import asyncio
import logging
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import TYPE_CHECKING

from simile.behaviour import IntentionBroken, IntentionKept, Options
from simile.conversation.loans import Loan
from simile.conversation.temptation import Lie
from simile.economy.loans import transfer
from simile.llm import LLMClient, LLMError, StructuredOutputError
from simile.memory import MemoryStore
from simile.reflection.config import DEFAULT_CONFIG, ReflectionConfig
from simile.reflection.extraction import SYSTEM, Context, Extraction, gather, prompt
from simile.reflection.intentions import broken, intentions, kept
from simile.reflection.loans import Payment, payment
from simile.reflection.outcome import Outcome, outcome
from simile.schema import Conversation, Id, Intention, Npc, Relationship
from simile.sim import Clock, ConversationEnded

if TYPE_CHECKING:
    from simile.economy.economy import Economy

logger = logging.getLogger(__name__)


def no_options(npc: Id) -> Options | None:
    return None


def no_plans(npc: Id) -> list[Intention]:
    return []


def ignore(intention: Intention) -> bool:
    return False


def no_lies(conversation_id: str) -> list[Lie]:
    return []


class Reflector:
    """Hears every `ConversationEnded` and, in a task, asks the LLM what it meant to each NPC in
    it, then stores their memories, the events, the flags and how they now feel. Moves the
    money of a loan the conversation was set up to settle through the `economy`. `settle` hands
    over that loan, by conversation id, and is called once for every conversation that ends.
    What each resident said they'd do goes to `intend`, checked against B1's `options`, and B1's
    `planned` says what they've said already. `lies` hands over, once, what B2 set residents up
    to lie about. `on_broken` and `on_kept` record what became of a promise."""

    def __init__(
        self,
        memory: MemoryStore,
        npcs: Callable[[], Mapping[Id, Npc]],
        llm: Callable[[], LLMClient | None],
        *,
        config: ReflectionConfig = DEFAULT_CONFIG,
        settle: Callable[[str], Loan | None] = lambda _: None,
        economy: "Callable[[], Economy | None]" = lambda: None,
        options: Callable[[Id], Options | None] = no_options,
        planned: Callable[[Id], list[Intention]] = no_plans,
        intend: Callable[[Intention], bool] = ignore,
        lies: Callable[[str], list[Lie]] = no_lies,
        clock: Clock | None = None,
    ) -> None:
        self.memory = memory
        self.npcs = npcs
        self.llm = llm
        self.config = config
        self.settle = settle
        self.economy = economy
        self.options = options
        self.planned = planned
        self.intend = intend
        self.lies = lies
        self.clock = clock
        self.tasks: set[asyncio.Task[Outcome | None]] = set()

    def on_ended(self, event: ConversationEnded) -> None:
        """Start reflecting on the conversation. Doesn't block."""
        conversation = event.conversation
        llm = self.llm()
        if not conversation.lines or llm is None:
            self.settle(conversation.id)
            self.lies(conversation.id)
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
        finally:
            self.settle(conversation.id)

    def on_broken(self, event: IntentionBroken) -> None:
        intention = event.intention
        if records := broken(intention, self.npcs(), self.memory, self._now(intention)):
            self.memory.add(*records)
            logger.info("%s broke a promise: %s", intention.owner, intention.description)

    def on_kept(self, event: IntentionKept) -> None:
        intention = event.intention
        if records := kept(intention, self.npcs(), self.memory, self._now(intention)):
            self.memory.add(*records)

    def _now(self, intention: Intention) -> datetime:
        return self.clock.now if self.clock else intention.expires

    async def stop(self) -> None:
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _reflect(self, llm: LLMClient, conversation: Conversation) -> Outcome | None:
        npcs = self.npcs()
        options = {
            npc: found
            for npc in conversation.participants
            if npc in npcs and (found := self.options(npc)) is not None
        }
        planned = {npc: self.planned(npc) for npc in options}
        context = gather(
            conversation,
            npcs,
            self.memory,
            self.config,
            options=options,
            planned=planned,
            lies=self.lies(conversation.id),
        )
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
        for intention in intentions(context, extraction, self.config):
            if self.intend(intention):
                result.intentions.append(intention)
                logger.info(
                    "%s: %s means to %s%s (%s): %s",
                    conversation.id,
                    intention.owner,
                    intention.kind.value,
                    f" {intention.target}" if intention.target else "",
                    intention.due.isoformat(),
                    intention.description,
                )
        return result

    def _pay(self, context: Context, extraction: Extraction) -> Payment | None:
        loan, economy = self.settle(context.conversation.id), self.economy()
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
