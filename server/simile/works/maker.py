import asyncio
import logging
import uuid
from collections.abc import Callable, Sequence
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, create_model

from simile.llm import LLMClient, StructuredOutputError
from simile.memory import MemoryStore
from simile.news.analysis import MEANINGS, SCALE, clean_tags
from simile.npc.values import format_scores, ranked
from simile.schema import CoreValue, Craft, Id, Medium, Memory, MemoryKind, Npc, Work
from simile.sim import Clock
from simile.works.config import DEFAULT_CONFIG, WorksConfig
from simile.works.store import WorksStore

logger = logging.getLogger(__name__)

FEELINGS = (
    (-0.5, "It upset you"),
    (-0.15, "It bothered you"),
    (0.15, "You had mixed feelings about it"),
    (0.5, "It pleased you"),
)


class Piece(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1)
    text: str = Field(min_length=1, description="The piece itself.")
    statement: str = Field(
        min_length=1, description="A sentence or two in your own voice on what it's saying."
    )
    inspired_by: list[int] = Field(
        description="The numbers of the things on your mind that it came from."
    )
    tags: list[str] = Field(
        description="Up to 10 short lowercase topic tags of one to three words."
    )
    sentiment: float = Field(
        ge=0, le=SCALE, description=f"Its overall tone, from 0 (very negative) to {SCALE}."
    )


Reply = create_model(
    "Piece",
    __base__=Piece,
    **{
        value.value: (float, Field(ge=0, le=SCALE, description=f"How closely it relates to {m}."))
        for value, m in MEANINGS.items()
    },
)


def system_prompt(npc: Npc, craft: Craft, config: WorksConfig = DEFAULT_CONFIG) -> str:
    order = ranked(npc.values)
    most = format_scores(order[: config.cares_most])
    least = format_scores(order[::-1][: config.cares_least])
    return (
        f"You are {npc.name} ({npc.age}, {npc.occupation}), who lives in a small village of "
        "2026 with delivery drones overhead, solar roofs and public news terminals. "
        f"{npc.persona}\n\n{npc.backstory}\n\n"
        f"Your values, scored 0 to 1. You care most about: {most}. You care least about: "
        f"{least}.\n"
        f"Your interests: {', '.join(npc.interests)}.\n"
        f"How you talk: {npc.speaking_style}\n\n"
        f"In your own time you write {craft.form}. They go up on the news terminals beside the "
        "news, for your neighbours to read. It's how you have your say in public."
    )


def feeling(memory: Memory) -> str:
    felt = next((text for below, text in FEELINGS if memory.valence < below), "It delighted you")
    strength = (
        ", and you keep coming back to it"
        if memory.salience >= 0.7
        else ", but it was a passing thing"
        if memory.salience < 0.3
        else ""
    )
    return f"({felt}{strength}.)"


def prompt(
    craft: Craft,
    memories: Sequence[Memory],
    past: Sequence[Work],
    config: WorksConfig = DEFAULT_CONFIG,
) -> str:
    if memories:
        mind = "What's been on your mind lately, strongest first:\n" + "\n".join(
            f"{n}. {m.content} {feeling(m)}" for n, m in enumerate(memories, 1)
        )
        start = "Start from one or more of the things on your mind, and say"
    else:
        mind = "Nothing in particular has been on your mind lately."
        start = "Say"
    works = (
        "\n\nYour last few pieces, newest first. Don't repeat yourself:\n"
        + "\n".join(f'- "{work.title}": {work.statement}' for work in past)
        if past
        else ""
    )
    return (
        f"{mind}{works}\n\n"
        f"Write something new in your craft, {craft.form}. {start} something in line with what you "
        "care about. Where you care strongly, take a side, even a provocative one: your "
        "neighbours should be able to tell where you stand, and guess it's yours without your "
        "name on it. Write in your own voice and the style of your craft, and keep it short: "
        f"{config.words} words at most.\n\n"
        "Then step outside the piece and analyse it: which of the numbered things on your mind "
        f"it came from, if any, its topic tags, its overall tone, and how closely it relates to "
        f"each of the 24 values, from 0 (not at all) to {SCALE} (it's what the piece is about). "
        "A score has no direction: a piece that attacks a value relates to it as much as one "
        "that upholds it. Most pieces relate closely to only a few values, so most scores "
        "should be 0 or low."
    )


def source(memory: Memory) -> str | None:
    return memory.work_id or memory.news_id or memory.conversation_id


def remember(npc: Npc, work: Work, config: WorksConfig) -> Memory:
    return Memory(
        owner=npc.id,
        kind=MemoryKind.WORK,
        content=f'I wrote "{work.title}" and put it up on the news terminals. {work.statement}',
        salience=config.salience,
        valence=config.valence,
        timestamp=work.created,
        topics=work.tags[: config.topics],
        work_id=work.id,
    )


class Maker:
    """Residents make works from what's on their mind: their strongest recent memories, their
    values and craft, and their own last few works. One LLM call writes the piece and analyses
    it, off the tick, and the artist remembers making it. Only writing for now."""

    def __init__(
        self,
        works: WorksStore,
        memory: MemoryStore,
        clock: Clock,
        llm: Callable[[], LLMClient | None],
        *,
        config: WorksConfig = DEFAULT_CONFIG,
    ) -> None:
        self.works = works
        self.memory = memory
        self.clock = clock
        self.llm = llm
        self.config = config
        self.making: set[Id] = set()
        self.tasks: set[asyncio.Task[Work | None]] = set()

    def make(self, npc: Npc) -> asyncio.Task[Work | None] | None:
        """Start `npc` writing a piece, unless they don't write, are writing one already, or
        there's no LLM. Doesn't block. The task stores the work and the artist's memory of
        making it and returns the work, or None if the call fails."""
        llm = self.llm()
        if llm is None or npc.craft is None or npc.craft.medium is not Medium.WRITING:
            return None
        if npc.id in self.making:
            return None
        self.making.add(npc.id)
        task = asyncio.get_running_loop().create_task(
            self._write(llm, npc, npc.craft, self.clock.now)
        )
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        task.add_done_callback(lambda _: self.making.discard(npc.id))
        return task

    async def stop(self) -> None:
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def on_mind(self, npc: Npc, now: datetime) -> tuple[list[Memory], list[Work]]:
        """`npc`'s strongest memories, leaving out making their own works, and their latest
        works."""
        theirs = self.works.by(npc.id)
        own = {work.id for work in theirs}
        recalled = self.memory.recall(
            npc.id, now, k=self.config.memories + len(own), half_life=self.config.half_life
        )
        memories = [m for m in recalled if m.work_id not in own][: self.config.memories]
        return memories, theirs[: self.config.past_works]

    async def _write(self, llm: LLMClient, npc: Npc, craft: Craft, now: datetime) -> Work | None:
        memories, past = self.on_mind(npc, now)
        try:
            reply = await llm.structured(
                prompt(craft, memories, past, self.config),
                Reply,
                system=system_prompt(npc, craft, self.config),
                model=self.config.model,
                purpose="work",
                priority=self.config.priority,
            )
        except StructuredOutputError:
            logger.warning("%s couldn't write a piece that fit, so made nothing", npc.id)
            return None
        except Exception:
            logger.warning("%s couldn't write a piece", npc.id, exc_info=True)
            return None
        sources = (source(memories[n - 1]) for n in reply.inspired_by if 1 <= n <= len(memories))
        work = Work(
            id=f"{npc.id}-{uuid.uuid4().hex[:8]}",
            artist=npc.id,
            medium=craft.medium,
            form=craft.form,
            title=reply.title,
            created=now,
            text=reply.text,
            statement=reply.statement,
            inspired_by=list(dict.fromkeys(id for id in sources if id)),
            values={value: getattr(reply, value.value) / SCALE for value in CoreValue},
            tags=clean_tags(reply.tags),
            sentiment=reply.sentiment / SCALE * 2 - 1,
        )
        self.works.add(work)
        self.memory.add(remember(npc, work, self.config))
        logger.info("%s wrote %r: %s", npc.id, work.title, work.statement)
        return work
