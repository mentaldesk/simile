import asyncio
import logging
import uuid
from collections.abc import Callable, Coroutine, Mapping, Sequence
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, create_model

from simile.llm import LLMClient, StructuredOutputError
from simile.memory import MemoryStore
from simile.news.analysis import MEANINGS, SCALE, clean_tags
from simile.npc.values import format_scores, ranked
from simile.schema import CoreValue, Craft, Id, Medium, Memory, MemoryKind, Npc, Work
from simile.sim import Clock
from simile.works.config import DEFAULT_CONFIG, WorksConfig
from simile.works.reading import name_of
from simile.works.render import canvas, draw, metres
from simile.works.store import WorksStore
from simile.works.svg import BadSvg, checked
from simile.works.walls import wall_name
from simile.world.map import MuralWall

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


class Mural(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1)
    description: str = Field(
        min_length=1, description="What it shows, in a few plain sentences, as a passer-by sees it."
    )
    statement: str = Field(
        min_length=1, description="A sentence or two in your own voice on what it's saying."
    )
    svg: str = Field(min_length=1, description="The mural, as one SVG document.")
    inspired_by: list[int] = Field(
        description="The numbers of the things on your mind that it came from."
    )
    tags: list[str] = Field(
        description="Up to 10 short lowercase topic tags of one to three words."
    )
    sentiment: float = Field(
        ge=0, le=SCALE, description=f"Its overall tone, from 0 (very negative) to {SCALE}."
    )


RELATES: dict[str, Any] = {
    value.value: (float, Field(ge=0, le=SCALE, description=f"How closely it relates to {m}."))
    for value, m in MEANINGS.items()
}
Reply = create_model("Piece", __base__=Piece, **RELATES)
MuralReply = create_model("Mural", __base__=Mural, **RELATES)


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
        + (
            f"In your own time you paint {craft.form} on the village's walls, where everyone who "
            "walks by sees them. It's how you have your say in public."
            if craft.medium is Medium.MURAL
            else f"In your own time you write {craft.form}. They go up on the news terminals "
            "beside the news, for your neighbours to read. It's how you have your say in public."
        )
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


def on_your_mind(memories: Sequence[Memory], past: Sequence[Work], works: str) -> tuple[str, str]:
    """What's on their mind and their last few works for a prompt, and how to start the ask."""
    if memories:
        mind = "What's been on your mind lately, strongest first:\n" + "\n".join(
            f"{n}. {m.content} {feeling(m)}" for n, m in enumerate(memories, 1)
        )
        start = "Start from one or more of the things on your mind, and say"
    else:
        mind = "Nothing in particular has been on your mind lately."
        start = "Say"
    if past:
        mind += f"\n\nYour last few {works}, newest first. Don't repeat yourself:\n" + "\n".join(
            f'- "{work.title}": {work.statement}' for work in past
        )
    return mind, start


def analysis(noun: str) -> str:
    return (
        f"Then step outside the {noun} and analyse it: which of the numbered things on your mind "
        f"it came from, if any, its topic tags, its overall tone, and how closely it relates to "
        f"each of the 24 values, from 0 (not at all) to {SCALE} (it's what the {noun} is about). "
        f"A score has no direction: a {noun} that attacks a value relates to it as much as one "
        f"that upholds it. Most {noun}s relate closely to only a few values, so most scores "
        "should be 0 or low."
    )


TAKE_A_SIDE = (
    "Where you care strongly, take a side, even a provocative one: your neighbours should be able "
    "to tell where you stand, and guess it's yours without your name on it."
)


def prompt(
    craft: Craft,
    memories: Sequence[Memory],
    past: Sequence[Work],
    config: WorksConfig = DEFAULT_CONFIG,
) -> str:
    mind, start = on_your_mind(memories, past, "pieces")
    return (
        f"{mind}\n\n"
        f"Write something new in your craft, {craft.form}. {start} something in line with what you "
        f"care about. {TAKE_A_SIDE} Write in your own voice and the style of your craft, and keep "
        f"it short: {config.words} words at most.\n\n{analysis('piece')}"
    )


def mural_prompt(
    craft: Craft,
    memories: Sequence[Memory],
    past: Sequence[Work],
    wall: MuralWall,
    on_it: str = "It's blank.",
    config: WorksConfig = DEFAULT_CONFIG,
) -> str:
    """`on_it` says what's on the wall now."""
    mind, start = on_your_mind(memories, past, "murals")
    width, height = canvas(wall)
    across, up = metres(wall)
    return (
        f"{mind}\n\n"
        f"You've come to paint a new mural on {wall_name(wall.id)}, {across:.1f} m wide and "
        f"{up:.1f} m high. {on_it}\n\n"
        f"Paint something new in your craft, {craft.form}. {start} something in line with what you "
        f"care about. {TAKE_A_SIDE} The composition, palette and style are yours.\n\n"
        f'Draw it as one SVG document with viewBox="0 0 {width} {height}", filling the whole '
        "canvas, since it's paint on a wall: no frame and no transparent background. Use only "
        "shapes, paths, text, gradients, patterns, clip paths, masks and filters. No scripts, "
        "<image>, <foreignObject> or links, and nothing that loads from outside the SVG. Keep it "
        f"under {config.svg_chars // 3:,} characters. Any words on it should be few, and big "
        "enough to read from across the street. Keep them well inside the edges, allowing each "
        "letter 0.7 of the font size, since the wall may not have your font.\n\n"
        "Describe what it shows in a few plain sentences, as a passer-by would see it, and say in "
        f"a sentence or two of your own what it's saying.\n\n{analysis('mural')}"
    )


def source(memory: Memory) -> str | None:
    return memory.work_id or memory.news_id or memory.conversation_id


def remember(npc: Npc, work: Work, config: WorksConfig, over: str = "") -> Memory:
    made = (
        f'I painted "{work.title}" on {wall_name(work.wall)}{over}.'
        if work.wall
        else f'I wrote "{work.title}" and put it up on the news terminals.'
    )
    return Memory(
        owner=npc.id,
        kind=MemoryKind.WORK,
        content=f"{made} {work.statement}",
        salience=config.salience,
        valence=config.valence,
        timestamp=work.created,
        topics=work.tags[: config.topics],
        work_id=work.id,
    )


def nothing_painted(work: Work) -> None:
    return None


class Maker:
    """Residents make works from what's on their mind: their strongest recent memories, their
    values and craft, and their own last few works. One LLM call makes the piece or mural and
    analyses it, off the tick, and the artist remembers making it."""

    def __init__(
        self,
        works: WorksStore,
        memory: MemoryStore,
        clock: Clock,
        llm: Callable[[], LLMClient | None],
        *,
        walls: Sequence[MuralWall] = (),
        npcs: Mapping[Id, Npc] | None = None,
        painted: Callable[[Work], None] = nothing_painted,
        config: WorksConfig = DEFAULT_CONFIG,
    ) -> None:
        self.works = works
        self.memory = memory
        self.clock = clock
        self.llm = llm
        self.walls = {wall.id: wall for wall in walls}
        self.npcs = npcs or {}
        self.painted = painted
        self.config = config
        self.making: set[Id] = set()
        self.tasks: set[asyncio.Task[Work | None]] = set()

    def make(self, npc: Npc, wall: Id | None = None) -> asyncio.Task[Work | None] | None:
        """Start `npc` writing a piece, or painting a mural on `wall`, unless they don't make
        that, are making something already, or there's no LLM. Doesn't block. The task stores
        the work and the artist's memory of making it and returns the work, or None if it
        fails."""
        llm, craft = self.llm(), npc.craft
        if llm is None or craft is None or npc.id in self.making:
            return None
        making: Coroutine[Any, Any, Work | None]
        if craft.medium is Medium.WRITING:
            making = self._write(llm, npc, craft, self.clock.now)
        elif wall in self.walls:
            making = self._paint(llm, npc, craft, self.walls[wall], self.clock.now)
        else:
            return None
        self.making.add(npc.id)
        task = asyncio.get_running_loop().create_task(self._guarded(npc, making))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        task.add_done_callback(lambda _: self.making.discard(npc.id))
        return task

    async def stop(self) -> None:
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _guarded(self, npc: Npc, making: Coroutine[Any, Any, Work | None]) -> Work | None:
        try:
            return await making
        except Exception:
            logger.exception("%s couldn't make anything", npc.id)
            return None

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
        ask = prompt(craft, memories, past, self.config)
        reply = await self._ask(llm, npc, craft, ask, Reply, "work")
        if reply is None:
            return None
        work = self._work(npc, craft, reply, reply.text, memories, now, uuid.uuid4().hex[:8])
        self.works.add(work)
        self.memory.add(remember(npc, work, self.config))
        logger.info("%s wrote %r: %s", npc.id, work.title, work.statement)
        return work

    async def _paint(
        self, llm: LLMClient, npc: Npc, craft: Craft, wall: MuralWall, now: datetime
    ) -> Work | None:
        memories, past = self.on_mind(npc, now)
        showing = self.works.showing().get(wall.id)
        on_it = "It's blank."
        if showing:
            who = "you" if showing.artist == npc.id else name_of(self.npcs, showing.artist)
            on_it = (
                f'You\'re painting over {self._whose(npc, showing)} "{showing.title}", of which '
                f'{who} said: "{showing.statement}"'
            )
        ask = first = mural_prompt(craft, memories, past, wall, on_it, self.config)
        key = uuid.uuid4().hex[:8]
        for _ in range(2):
            reply = await self._ask(llm, npc, craft, ask, MuralReply, "mural")
            if reply is None:
                return None
            try:
                svg, png = await self._picture(reply.svg, wall, int(key, 16))
                break
            except BadSvg as error:
                logger.info("%s's mural for %s won't do: %s", npc.id, wall.id, error)
                ask = f"{first}\n\nYour last try couldn't go up, because {error}. Fix that."
        else:
            logger.warning("%s couldn't paint a mural that would go up, so made nothing", npc.id)
            return None
        work = self._work(npc, craft, reply, reply.description, memories, now, key, wall.id)
        covered = self.works.paint(work, svg, png)
        over = f' over {self._whose(npc, covered, "my")} "{covered.title}"' if covered else ""
        self.memory.add(remember(npc, work, self.config, over))
        logger.info("%s painted %r on %s: %s", npc.id, work.title, wall.id, work.statement)
        self.painted(work)
        return work

    async def _picture(self, svg: str, wall: MuralWall, seed: int) -> tuple[str, bytes]:
        width, height = canvas(wall)
        config = self.config
        svg = checked(
            svg,
            width,
            height,
            chars=config.svg_chars,
            elements=config.svg_elements,
            tolerance=config.aspect_tolerance,
        )
        png = await asyncio.to_thread(
            draw, svg, width, height, seed=seed, timeout=config.render_timeout
        )
        return svg, png

    async def _ask[R: BaseModel](
        self, llm: LLMClient, npc: Npc, craft: Craft, ask: str, reply: type[R], purpose: str
    ) -> R | None:
        try:
            return await llm.structured(
                ask,
                reply,
                system=system_prompt(npc, craft, self.config),
                model=self.config.model,
                purpose=purpose,
                priority=self.config.priority,
            )
        except StructuredOutputError:
            logger.warning("%s couldn't make a %s that fit, so made nothing", npc.id, purpose)
        except Exception:
            logger.warning("%s couldn't make a %s", npc.id, purpose, exc_info=True)
        return None

    def _work(
        self,
        npc: Npc,
        craft: Craft,
        reply: Piece | Mural,
        text: str,
        memories: Sequence[Memory],
        now: datetime,
        key: str,
        wall: Id | None = None,
    ) -> Work:
        sources = (source(memories[n - 1]) for n in reply.inspired_by if 1 <= n <= len(memories))
        return Work(
            id=f"{npc.id}-{key}",
            artist=npc.id,
            medium=craft.medium,
            form=craft.form,
            title=reply.title,
            created=now,
            text=text,
            statement=reply.statement,
            inspired_by=list(dict.fromkeys(id for id in sources if id)),
            values={value: getattr(reply, value.value) / SCALE for value in CoreValue},
            tags=clean_tags(reply.tags),
            sentiment=reply.sentiment / SCALE * 2 - 1,
            wall=wall,
        )

    def _whose(self, npc: Npc, work: Work, own: str = "your own") -> str:
        return own if work.artist == npc.id else f"{name_of(self.npcs, work.artist)}'s"
