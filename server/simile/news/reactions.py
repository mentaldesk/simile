import asyncio
import logging
import sys
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field

from simile.llm import LLMClient, Model, StructuredOutputError
from simile.memory import MemoryStore
from simile.memory.store import recency
from simile.news.store import NewsStore
from simile.npc.values import format_scores, ranked
from simile.schema import Id, Memory, MemoryKind, NewsItem, Npc, Signed, Unit
from simile.sim import Clock

logger = logging.getLogger(__name__)


class NewsConfig(BaseModel):
    """Every constant of how NPCs read and bring up the news."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    per_visit: int = Field(
        default=2, ge=1, description="Articles read per terminal visit, newest unread first."
    )
    model: str = Field(default=Model.HAIKU_5_5, description="The model that rates each article.")
    priority: int = Field(
        default=-1, description="L1 priority of the rating calls, below conversations' 0."
    )
    cares_most: int = Field(
        default=5, ge=0, description="Strongest values listed in the reading prompt."
    )
    cares_least: int = Field(
        default=3, ge=0, description="Weakest values listed in the reading prompt."
    )
    topics: int = Field(default=3, ge=0, description="Most topics kept per reaction.")
    half_life: timedelta = Field(
        default=timedelta(hours=24),
        description="Sim time over which a reaction's pull as a topic halves.",
    )
    min_score: float = Field(
        default=0.05,
        ge=0,
        description="Reactions scoring less than this (intensity × recency) aren't raised.",
    )


DEFAULT_CONFIG = NewsConfig()


class Reaction(BaseModel):
    take: str = Field(
        description="What you make of it in one short sentence, in your own voice, as you'd say "
        "it to a neighbour."
    )
    valence: Signed = Field(
        description="-1 if it goes against everything you care about, 1 if it's exactly what "
        "you hoped to hear, 0 if neither."
    )
    intensity: Unit = Field(
        description="How strongly it hits you, 0 (a shrug) to 1 (you can't stop thinking about it)."
    )
    topics: list[str] = Field(
        description="One to three short lowercase topics it's about, e.g. 'privacy'."
    )


def system_prompt(npc: Npc, config: NewsConfig = DEFAULT_CONFIG) -> str:
    order = ranked(npc.values)
    most = format_scores(order[: config.cares_most])
    least = format_scores(order[::-1][: config.cares_least])
    return (
        f"You are {npc.name} ({npc.age}, {npc.occupation}), who lives in a small village. "
        f"{npc.persona}\n\n"
        f"Your values, scored 0 to 1. You care most about: {most}. You care least about: "
        f"{least}.\n"
        f"Your interests: {', '.join(npc.interests)}.\n"
        f"How you talk: {npc.speaking_style}"
    )


def read_in(item: NewsItem) -> str:
    return f" in {item.source}" if item.source else ""


def article_prompt(item: NewsItem) -> str:
    return (
        f"You've just read this{read_in(item)} on the village news terminal.\n\n"
        f"{item.title}\n{item.summary}\n\n"
        "How does it land with you? Something that chimes with what you care about most is "
        "strongly positive, something that goes against it strongly negative, and something "
        "you don't care about is mild either way."
    )


def remember(
    npc: Npc, item: NewsItem, reaction: Reaction, now: datetime, config: NewsConfig
) -> Memory:
    topics = [topic.strip().lower() for topic in reaction.topics if topic.strip()]
    return Memory(
        owner=npc.id,
        kind=MemoryKind.NEWS,
        content=f'I read "{item.title}"{read_in(item)} on the news terminal. '
        f"{reaction.take.strip()}",
        salience=reaction.intensity,
        valence=reaction.valence,
        timestamp=now,
        topics=topics[: config.topics],
        news_id=item.id,
    )


class NewsReader:
    """B1's `read_news` hook: an NPC at a terminal reads the latest articles they haven't read,
    and a task asks the LLM how each lands and stores it as a `news` memory."""

    def __init__(
        self,
        news: NewsStore,
        memory: MemoryStore,
        clock: Clock,
        llm: Callable[[], LLMClient | None],
        *,
        config: NewsConfig = DEFAULT_CONFIG,
    ) -> None:
        self.news = news
        self.memory = memory
        self.clock = clock
        self.llm = llm
        self.config = config
        self.seen: dict[Id, set[str]] = {}
        self.tasks: set[asyncio.Task[None]] = set()

    def read(self, npc: Npc) -> None:
        """Pick the articles `npc` reads now and start reacting to them. Doesn't block."""
        llm = self.llm()
        if llm is None:
            return
        loop = asyncio.get_running_loop()
        seen = self._seen_by(npc.id)
        items = self.news.latest(self.config.per_visit, exclude=seen)
        if not items:
            return
        seen.update(item.id for item in items)
        task = loop.create_task(self._react(llm, npc, items, self.clock.now))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def stop(self) -> None:
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def _seen_by(self, npc: Id) -> set[str]:
        if npc not in self.seen:
            memories = self.memory.recall(npc, self.clock.now, kind=MemoryKind.NEWS, k=sys.maxsize)
            self.seen[npc] = {memory.news_id for memory in memories if memory.news_id}
        return self.seen[npc]

    async def _react(
        self, llm: LLMClient, npc: Npc, items: Sequence[NewsItem], now: datetime
    ) -> None:
        for index, item in enumerate(items):
            try:
                reaction = await llm.structured(
                    article_prompt(item),
                    Reaction,
                    system=system_prompt(npc, self.config),
                    model=self.config.model,
                    purpose="news-reaction",
                    priority=self.config.priority,
                )
            except StructuredOutputError:
                logger.warning("%s couldn't rate %r, so skipped it", npc.id, item.title)
                continue
            except Exception:
                logger.warning("%s couldn't read %r", npc.id, item.title, exc_info=True)
                self.seen[npc.id].difference_update(unread.id for unread in items[index:])
                return
            self.memory.add(remember(npc, item, reaction, now, self.config))
            logger.info(
                "%s read %r: valence %.2f, intensity %.2f. %s",
                npc.id,
                item.title,
                reaction.valence,
                reaction.intensity,
                reaction.take,
            )


def score(memory: Memory, now: datetime, half_life: timedelta) -> float:
    age = (now - memory.timestamp).total_seconds()
    return memory.salience * recency(age, half_life.total_seconds())


def topics_to_raise(
    memory: MemoryStore,
    npc_id: str,
    now: datetime,
    k: int = 3,
    *,
    config: NewsConfig = DEFAULT_CONFIG,
) -> list[Memory]:
    """`npc_id`'s `news` memories ranked by recency × intensity, best first, leaving out those
    that have faded below `config.min_score`."""
    recalled = memory.recall(npc_id, now, kind=MemoryKind.NEWS, k=k, half_life=config.half_life)
    return [m for m in recalled if score(m, now, config.half_life) >= config.min_score]
