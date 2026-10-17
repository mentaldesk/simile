import asyncio
import logging
import sys
from collections.abc import Callable, Mapping
from datetime import datetime

from pydantic import BaseModel, Field

from simile.behaviour import NewsInterest, NewsReader
from simile.behaviour.scoring import affinity
from simile.llm import LLMClient, StructuredOutputError
from simile.memory import MemoryStore
from simile.news.interest import interest as article_interest
from simile.news.reactions import system_prompt
from simile.schema import Id, Medium, Memory, MemoryKind, Npc, Relationship, Signed, Unit, Work
from simile.sim import Clock
from simile.social import as_of, describe, meet
from simile.works.config import DEFAULT_CONFIG, WorksConfig
from simile.works.store import WorksStore

logger = logging.getLogger(__name__)


class Reaction(BaseModel):
    take: str = Field(
        description="What you make of it in one short sentence, in your own voice, as you'd say "
        "it to a neighbour."
    )
    valence: Signed = Field(
        description="-1 if it goes against everything you care about, 1 if it says exactly what "
        "you'd want said, 0 if neither."
    )
    intensity: Unit = Field(
        description="How strongly it hits you, 0 (a shrug) to 1 (you can't stop thinking about it)."
    )


def name_of(npcs: Mapping[Id, Npc], id: Id) -> str:
    npc = npcs.get(id)
    return npc.name if npc else id.title()


def interest(
    reader: Npc, work: Work, feeling: Relationship, config: WorksConfig = DEFAULT_CONFIG
) -> float:
    return article_interest(reader, work) + config.artist_weight * affinity(feeling)


def how_it_lands(artist: str) -> str:
    return (
        f"How does it land with you, given what you care about and how you feel about {artist}? "
        "Something that chimes with what you care about most is strongly positive, something "
        "that goes against it strongly negative, and something you don't care about is mild "
        "either way."
    )


def work_prompt(work: Work, artist: str, feeling: str) -> str:
    return (
        f"You've just read this on the village news terminal, where your neighbours put up what "
        f"they write. It's by {artist}, who writes {work.form}.\n\n"
        f"{work.title}\n\n{work.text}\n\n"
        f"{artist} says of it: {work.statement}\n\n{feeling}\n\n{how_it_lands(artist)}"
    )


def remember(
    npc: Npc, work: Work, artist: str, reaction: Reaction, now: datetime, config: WorksConfig
) -> Memory:
    return Memory(
        owner=npc.id,
        kind=MemoryKind.WORK,
        content=f'I read {artist}\'s "{work.title}" on the news terminal. {reaction.take.strip()}',
        salience=reaction.intensity,
        valence=reaction.valence,
        timestamp=now,
        about=[work.artist],
        topics=work.tags[: config.topics],
        work_id=work.id,
    )


class WorksReader:
    """B1's `news_interest` and `read_news` hooks, wrapped around the news's."""

    def __init__(
        self,
        works: WorksStore,
        memory: MemoryStore,
        clock: Clock,
        llm: Callable[[], LLMClient | None],
        npcs: Mapping[Id, Npc],
        *,
        news_interest: NewsInterest,
        read_news: NewsReader,
        config: WorksConfig = DEFAULT_CONFIG,
    ) -> None:
        self.works = works
        self.memory = memory
        self.clock = clock
        self.llm = llm
        self.npcs = npcs
        self.news_interest = news_interest
        self.read_news = read_news
        self.config = config
        self.seen: dict[Id, set[str]] = {}
        self.tasks: set[asyncio.Task[None]] = set()

    def ranked(self, npc: Npc) -> list[tuple[Work, float]]:
        """Unread writing by others worth reading, most interesting first."""
        seen = self._seen_by(npc.id)
        works = [
            work
            for work in self.works.latest(Medium.WRITING, self.config.candidates)
            if work.artist != npc.id and work.id not in seen
        ]
        feelings = {artist: self._feeling(npc, artist) for artist in {w.artist for w in works}}
        scored = [(work, interest(npc, work, feelings[work.artist], self.config)) for work in works]
        worth = [pair for pair in scored if pair[1] >= self.config.min_interest]
        return sorted(worth, key=lambda pair: pair[1], reverse=True)

    def interest(self, npc: Npc) -> float:
        """How interesting `npc` finds the best article or work they haven't read, 0-1."""
        return max(self.news_interest(npc), self._best(npc)[1])

    def read(self, npc: Npc) -> None:
        """The best unread work if no article interests `npc` more, and the news's pick as well."""
        work, best = self._best(npc)
        llm = self.llm()
        if work is not None and llm is not None and best >= self.news_interest(npc):
            self._seen_by(npc.id).add(work.id)
            task = asyncio.get_running_loop().create_task(
                self._react(llm, npc, work, self.clock.now)
            )
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
        self.read_news(npc)

    async def stop(self) -> None:
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def _best(self, npc: Npc) -> tuple[Work | None, float]:
        if self.llm() is None:
            return None, 0.0
        best = self.ranked(npc)
        return (best[0][0], min(best[0][1], 1.0)) if best else (None, 0.0)

    def _feeling(self, npc: Npc, artist: Id) -> Relationship:
        rel = self.memory.relationship(npc.id, artist) or meet(npc, artist)
        return as_of(rel, self.clock.now)

    def _seen_by(self, npc: Id) -> set[str]:
        if npc not in self.seen:
            memories = self.memory.recall(npc, self.clock.now, kind=MemoryKind.WORK, k=sys.maxsize)
            self.seen[npc] = {memory.work_id for memory in memories if memory.work_id}
        return self.seen[npc]

    async def _react(self, llm: LLMClient, npc: Npc, work: Work, now: datetime) -> None:
        artist = name_of(self.npcs, work.artist)
        feeling = describe(self._feeling(npc, work.artist), artist)
        try:
            reaction = await llm.structured(
                work_prompt(work, artist, feeling),
                Reaction,
                system=system_prompt(npc),
                model=self.config.reaction_model,
                purpose="work-reaction",
                priority=self.config.priority,
            )
        except StructuredOutputError:
            logger.warning("%s couldn't rate %r, so skipped it", npc.id, work.title)
            return
        except Exception:
            logger.warning("%s couldn't read %r", npc.id, work.title, exc_info=True)
            self.seen[npc.id].discard(work.id)
            return
        self.memory.add(remember(npc, work, artist, reaction, now, self.config))
        logger.info(
            "%s read %s's %r: valence %.2f, intensity %.2f. %s",
            npc.id,
            work.artist,
            work.title,
            reaction.valence,
            reaction.intensity,
            reaction.take,
        )
