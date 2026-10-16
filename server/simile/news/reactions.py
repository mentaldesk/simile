import asyncio
import logging
import re
import sys
from collections.abc import Callable
from datetime import datetime, timedelta

from pydantic import BaseModel, Field

from simile.llm import LLMClient, StructuredOutputError
from simile.memory import MemoryStore
from simile.memory.store import recency
from simile.news.config import DEFAULT_CONFIG, NewsConfig
from simile.news.interest import interest, shared, words
from simile.news.store import NewsStore
from simile.npc.values import format_scores, ranked
from simile.schema import Id, Memory, MemoryKind, NewsItem, Npc, Signed, Unit
from simile.sim import Clock

logger = logging.getLogger(__name__)

TITLE = re.compile(r'^I read "(.+?)"')
NAMING = re.compile(r"\b(?:news|articles?|pieces?|story|stories|headlines?|read|papers?)\b", re.I)


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
    """B1's `read_news` and `news_interest` hooks: an NPC at a terminal reads the analysed
    article they haven't read that interests them most, and a task asks the LLM how it lands and
    stores it as a `news` memory."""

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

    def ranked(self, npc: Npc) -> list[tuple[NewsItem, float]]:
        """The analysed articles among the newest that `npc` hasn't read, with their interest,
        most interesting first. Those below `config.min_interest` are left out."""
        items = self.news.latest(
            self.config.candidates, exclude=self._seen_by(npc.id), analysed=True
        )
        scored = [(item, interest(npc, item, self.config)) for item in items]
        worth = [pair for pair in scored if pair[1] >= self.config.min_interest]
        return sorted(worth, key=lambda pair: pair[1], reverse=True)

    def interest(self, npc: Npc) -> float:
        """How interesting `npc` finds the best article they haven't read, 0-1. 0 if nothing is
        worth reading, or there's no LLM to read it with."""
        if self.llm() is None:
            return 0.0
        best = self.ranked(npc)
        return min(best[0][1], 1.0) if best else 0.0

    def read(self, npc: Npc) -> None:
        """Start reading the unread article that interests `npc` most, if any. Doesn't block."""
        llm = self.llm()
        if llm is None:
            return
        best = self.ranked(npc)
        if not best:
            return
        item = best[0][0]
        self._seen_by(npc.id).add(item.id)
        task = asyncio.get_running_loop().create_task(self._react(llm, npc, item, self.clock.now))
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

    async def _react(self, llm: LLMClient, npc: Npc, item: NewsItem, now: datetime) -> None:
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
            return
        except Exception:
            logger.warning("%s couldn't read %r", npc.id, item.title, exc_info=True)
            self.seen[npc.id].discard(item.id)
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


def mentioned(
    memory: MemoryStore,
    npc_id: str,
    said: str,
    now: datetime,
    *,
    article: Callable[[str], NewsItem | None] = lambda _: None,
    config: NewsConfig = DEFAULT_CONFIG,
) -> list[Memory]:
    """`npc_id`'s `news` memories of the articles `said` mentions, most shared words first, at
    most `config.mentions`. An article counts if its title, tags, summary and the NPC's topics
    share `config.mention_words` of the words in `said`, or if `said` names the news ("the Mars
    piece") and its title or a one-word tag or topic has one of them exactly, give or take a
    plural."""
    names_news = NAMING.search(said) is not None
    spoken = words(NAMING.sub(" ", said))
    if not spoken or not config.mentions:
        return []
    read = memory.recall(
        npc_id, now, kind=MemoryKind.NEWS, k=sys.maxsize, half_life=config.half_life
    )
    found = []
    for m in read:
        headline, whole = article_words(m, article(m.news_id) if m.news_id else None)
        n = shared(spoken, whole)
        if n >= config.mention_words or (names_news and spoken & headline):
            found.append((n, m))
    found.sort(key=lambda pair: -pair[0])
    return [m for _, m in found[: config.mentions]]


def article_words(memory: Memory, item: NewsItem | None) -> tuple[set[str], set[str]]:
    """The words of the article's title and of its one-word tags and NPC's topics, and those of
    all of it: title, tags, summary and topics. Without the article, the title in the memory."""
    if item is None:
        quoted = TITLE.match(memory.content)
        title, tags, summary = quoted[1] if quoted else memory.content, [], ""
    else:
        title, tags, summary = item.title, item.tags, item.summary
    labels = [*tags, *memory.topics]
    headline = words(" ".join([title, *(label for label in labels if label.isalpha())]))
    return headline, headline | words(" ".join([*labels, summary]))
