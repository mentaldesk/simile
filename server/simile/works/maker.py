import asyncio
import logging
import random
import uuid
from collections.abc import Callable, Coroutine, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, create_model

from simile.characters.humour import describe_humour
from simile.llm import LLMClient, StructuredOutputError
from simile.memory import MemoryStore
from simile.memory.store import recency
from simile.news.analysis import MEANINGS, SCALE, clean_tags
from simile.npc.values import format_scores, ranked
from simile.schema import (
    PLAYER_ID,
    CoreValue,
    Craft,
    HumourStyle,
    Id,
    Intention,
    Medium,
    Memory,
    MemoryKind,
    Npc,
    Work,
)
from simile.sim import Clock
from simile.works.config import DEFAULT_CONFIG, WorksConfig
from simile.works.painter import Painter, PaintingFailed, image_prompt
from simile.works.reading import name_of
from simile.works.render import PAINTING_M, canvas, draw, finish, metres, painting_canvas
from simile.works.store import WorksStore
from simile.works.svg import BadSvg, checked
from simile.works.walls import wall_name
from simile.world.map import MuralWall

logger = logging.getLogger(__name__)

VISITOR = "Visitor"
"""What the player is called in prompts, as in B2 and B3."""

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


class Painting(Mural):
    description: str = Field(
        min_length=1,
        description="What it shows, in a few plain sentences, as a visitor to the gallery sees it.",
    )
    svg: str = Field(min_length=1, description="The painting, as one SVG document.")


type Hang = Callable[[Work, str, bytes], None]
"""Hangs a painting in the gallery, given its SVG and PNG. A painted one has no SVG."""

RELATES: dict[str, Any] = {
    value.value: (float, Field(ge=0, le=SCALE, description=f"How closely it relates to {m}."))
    for value, m in MEANINGS.items()
}
Reply = create_model("Piece", __base__=Piece, **RELATES)
MuralReply = create_model("Mural", __base__=Mural, **RELATES)
PaintingReply = create_model("Painting", __base__=Painting, **RELATES)


def pictured(model: type[Mural], name: str) -> type[BaseModel]:
    """`model` with a description of the picture for the image model where its SVG was."""
    fields: dict[str, Any] = {}
    for key, info in model.model_fields.items():
        if key == "svg":
            fields["picture"] = (
                str,
                Field(min_length=1, description="The picture to paint, described for a painter."),
            )
        else:
            fields[key] = (info.annotation, info)
    return create_model(name, __config__=model.model_config, **fields, **RELATES)


MuralPictureReply = pictured(Mural, "Mural")
PaintingPictureReply = pictured(Painting, "Painting")
DRAWN = {Medium.MURAL: MuralReply, Medium.PAINTING: PaintingReply}
PAINTED = {Medium.MURAL: MuralPictureReply, Medium.PAINTING: PaintingPictureReply}
GOES_UP = {Medium.MURAL: "go up", Medium.PAINTING: "be hung"}


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
        f"How you talk: {npc.speaking_style}\n{your_humour(npc)}\n"
        + {
            Medium.MURAL: f"In your own time you paint {craft.form} on the village's walls, where "
            "everyone who walks by sees them. It's how you have your say in public.",
            Medium.PAINTING: f"In your own time you paint {craft.form}. They hang in the village "
            "gallery, where your neighbours come to look at them. It's how you have your say in "
            "public.",
            Medium.WRITING: f"In your own time you write {craft.form}. They go up on the news "
            "terminals beside the news, for your neighbours to read: stories and poems of your "
            "own making, not news or opinion.",
        }[craft.medium]
    )


def your_humour(npc: Npc) -> str:
    """Their humour on a line of its own, which can show in their work, or nothing without one."""
    if npc.humour is None:
        return ""
    shows = "" if npc.humour.style is HumourStyle.NONE else " It can show in your work too."
    return f"{describe_humour(npc.humour, kind=True)}{shows}\n"


@dataclass(frozen=True)
class Seed:
    """A spark drawn at random for each work, so the village's works don't all circle one idea."""

    genre: str
    subject: str
    mood: str

    def __str__(self) -> str:
        return f"{self.genre}, with {self.subject} at its heart, {self.mood} in mood"


def draw_seed(medium: Medium, rng: random.Random, config: WorksConfig = DEFAULT_CONFIG) -> Seed:
    genres = config.writing_genres if medium is Medium.WRITING else config.picture_genres
    return Seed(rng.choice(genres), rng.choice(config.subjects), rng.choice(config.moods))


@dataclass(frozen=True)
class Commission:
    """What a new work starts from: what's on the artist's mind, their own latest works, their
    neighbours' latest, a seed, and the idea they said they'd make, if any."""

    memories: Sequence[Memory]
    past: Sequence[Work]
    village: Sequence[Work]
    seed: Seed
    idea: str | None = None
    names: Mapping[Id, Npc] = field(default_factory=dict)


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


def gist(work: Work, words: int = 12) -> str:
    """A few words on what a work is about: its first tags, or else the start of its statement."""
    if work.tags:
        return ", ".join(work.tags[:3])
    said = work.statement.split()
    return " ".join(said[:words]) + ("…" if len(said) > words else "")


def on_your_mind(commission: Commission, works: str) -> str:
    """What's on their mind, the idea they said they'd make, their last few works and their
    neighbours' latest, for a prompt."""
    if commission.memories:
        mind = "What's been on your mind lately, strongest first:\n" + "\n".join(
            f"{n}. {m.content} {feeling(m)}" for n, m in enumerate(commission.memories, 1)
        )
    else:
        mind = "Nothing in particular has been on your mind lately."
    if commission.idea:
        mind = f"{commission.idea}\n\n{mind}"
    if commission.past:
        mind += f"\n\nYour last few {works}, newest first. Don't repeat yourself:\n" + "\n".join(
            f'- "{work.title}": {work.statement}' for work in commission.past
        )
    if commission.village:
        mind += (
            "\n\nYour neighbours' latest works, newest first. Make yours unlike them, in its "
            "subject, its images and its feeling:\n"
            + "\n".join(
                f'- "{work.title}", {name_of(commission.names, work.artist)}\'s '
                f"{work.medium.value}: {gist(work)}"
                for work in commission.village
            )
        )
    return mind


def start(commission: Commission) -> str:
    """How to start the ask for a mural or painting."""
    if commission.idea:
        return "Make that idea, in your own way, drawing on what's on your mind, and say"
    if commission.memories:
        return "Start from one or more of the things on your mind, and say"
    return "Say"


def spark(seed: Seed) -> str:
    return (
        f"For a spark this time, try {seed}. Take it wherever your craft and what's on your "
        "mind lead."
    )


def knowing(making: str) -> str:
    return (
        "You know what someone with your life and job would know. Stay within it: "
        f"{making} from your own life, work and village, never as an expert on what you don't "
        "know."
    )


def analysis(noun: str) -> str:
    return (
        f"Then step outside the {noun} and analyse it: which of the numbered things on your mind "
        f"it came from, if any, its topic tags, its overall tone, and how closely it relates to "
        f"each of the 24 values, from 0 (not at all) to {SCALE} (it's what the {noun} is about). "
        f"A score has no direction: a {noun} that attacks a value relates to it as much as one "
        f"that upholds it. Most {noun}s relate closely to only a few values, so most scores "
        "should be 0 or low."
    )


def svg_rules(config: WorksConfig) -> str:
    return (
        "Use only shapes, paths, text, gradients, patterns, clip paths, masks and filters. No "
        "scripts, <image>, <foreignObject> or links, and nothing that loads from outside the SVG. "
        f"Keep it under {config.svg_chars // 3:,} characters."
    )


TAKE_A_SIDE = (
    "Where you care strongly, take a side, even a provocative one: your neighbours should be able "
    "to tell where you stand, and guess it's yours without your name on it."
)

TONE = (
    "Keep it fit for every neighbour who sees it, children too: no violence, weapons or blood, "
    "nothing frightening or gruesome, and nothing adult or suggestive."
)


def picture_rules(config: WorksConfig) -> str:
    return (
        "It's painted from your description alone, taken literally, so describe the picture "
        "itself in plain, concrete words: what's in it and where, its colours and the style of "
        f"your craft, in {config.picture_words} words at most. Put no words, letters, numbers, "
        f"signs or logos in it: let the images say it. {TONE}"
    )


def idea(intention: Intention | None, npcs: Mapping[Id, Npc]) -> str | None:
    """The idea they said they'd make, to lead the prompt."""
    if intention is None:
        return None
    told = [VISITOR if id == PLAYER_ID else name_of(npcs, id) for id in intention.promised_to]
    said = f"You told {', '.join(told)} you'd make this" if told else "You meant to make this"
    return f"{said}, and you're making it now: {intention.description}"


def prompt(craft: Craft, commission: Commission, config: WorksConfig = DEFAULT_CONFIG) -> str:
    if commission.idea:
        grow = (
            "Make that idea, in your own way, drawing on what's on your mind and what you care "
            "about."
        )
    elif commission.memories:
        grow = "Let it grow from a mix of the things on your mind and what you care about."
    else:
        grow = "Let it grow from what you care about."
    return (
        f"{on_your_mind(commission, 'pieces')}\n\n"
        f"Write something new in your craft, {craft.form}: a piece of fiction or poetry, not an "
        f"opinion piece, advice or a notice. {grow} Make it about a person, a place or a moment "
        "rather than a stance, and let what you care about show in it rather than argue for it. "
        f"{spark(commission.seed)}\n\n{knowing('write')}\n\n"
        f"Write in your own voice and the style of your craft, and keep it short: {config.words} "
        f"words at most.\n\n{analysis('piece')}"
    )


def mural_prompt(
    craft: Craft,
    commission: Commission,
    wall: MuralWall,
    on_it: str = "It's blank.",
    config: WorksConfig = DEFAULT_CONFIG,
    *,
    painted: bool = False,
) -> str:
    """`on_it` says what's on the wall now. `painted` asks for the picture described for the
    image model rather than drawn as SVG."""
    width, height = canvas(wall)
    across, up = metres(wall)
    if painted:
        how = f"Describe the picture you'll paint, filling the whole wall. {picture_rules(config)}"
    else:
        how = (
            f'Draw it as one SVG document with viewBox="0 0 {width} {height}", filling the whole '
            "canvas, since it's paint on a wall: no frame and no transparent background. "
            f"{svg_rules(config)} Any words on it should be few, and big enough to read from "
            "across the street. Keep them well inside the edges, allowing each letter 0.7 of the "
            "font size, since the wall may not have your font."
        )
    return (
        f"{on_your_mind(commission, 'murals')}\n\n"
        f"You've come to paint a new mural on {wall_name(wall.id)}, {across:.1f} m wide and "
        f"{up:.1f} m high. {on_it}\n\n"
        f"Paint something new in your craft, {craft.form}. {start(commission)} something in line "
        f"with what you care about. {TAKE_A_SIDE} {spark(commission.seed)} The composition, "
        f"palette and style are yours.\n\n{knowing('paint')}\n\n{how}\n\n"
        "Describe what it shows in a few plain sentences, as a passer-by would see it, and say in "
        f"a sentence or two of your own what it's saying.\n\n{analysis('mural')}"
    )


def painting_prompt(
    craft: Craft,
    commission: Commission,
    config: WorksConfig = DEFAULT_CONFIG,
    *,
    painted: bool = False,
) -> str:
    """For a painter, or a muralist painting a canvas for once. `painted` as for murals."""
    width, height = painting_canvas()
    across, up = PAINTING_M
    what = (
        f"in the spirit of your craft, {craft.form}, but on canvas this time"
        if craft.medium is Medium.MURAL
        else f"in your craft, {craft.form}"
    )
    if painted:
        how = (
            "Describe the picture you'll paint, filling the whole canvas, since it hangs in a "
            "frame. Visitors see it close up, so detail rewards them. "
            f"{picture_rules(config)}"
        )
    else:
        how = (
            f'Draw it as one SVG document with viewBox="0 0 {width} {height}", filling the whole '
            "canvas: no frame, since it hangs in one, and no transparent background. "
            f"{svg_rules(config)} Visitors see it close up, so detail rewards them. Any words on "
            "it should be few. Keep them well inside the edges, allowing each letter 0.7 of the "
            "font size, since the gallery may not have your font."
        )
    return (
        f"{on_your_mind(commission, 'works')}\n\n"
        f"You're painting a canvas for the village gallery, {across:.2f} m wide and {up:.2f} m "
        f"high, to hang beside your neighbours' work. Paint something new {what}. "
        f"{start(commission)} something in line with what you care about. {TAKE_A_SIDE} "
        f"{spark(commission.seed)} The composition, palette and style are yours.\n\n"
        f"{knowing('paint')}\n\n{how}\n\n"
        "Describe what it shows in a few plain sentences, as a visitor would see it, and say in "
        f"a sentence or two of your own what it's saying.\n\n{analysis('painting')}"
    )


def source(memory: Memory) -> str | None:
    return memory.work_id or memory.news_id or memory.conversation_id


def remember(npc: Npc, work: Work, config: WorksConfig, over: str = "") -> Memory:
    if work.wall:
        made = f'I painted "{work.title}" on {wall_name(work.wall)}{over}.'
    elif work.medium is Medium.PAINTING:
        made = f'I painted "{work.title}" for the gallery.'
    else:
        made = f'I wrote "{work.title}" and put it up on the news terminals.'
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
    values and craft, their own last few works and their neighbours', and a random seed. One LLM
    call makes the piece or mural and analyses it, off the tick, and the artist remembers making
    it."""

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
        hang: Hang | None = None,
        painter: Painter | None = None,
        rng: random.Random | None = None,
        config: WorksConfig = DEFAULT_CONFIG,
    ) -> None:
        """Without `hang`, nobody paints for the gallery. With `painter`, murals and paintings
        are painted from a description, and drawn as SVG if that fails. `rng` draws each work's
        seed."""
        self.works = works
        self.memory = memory
        self.clock = clock
        self.llm = llm
        self.walls = {wall.id: wall for wall in walls}
        self.npcs = npcs or {}
        self.painted = painted
        self.hang = hang
        self.painter = painter
        self.rng = rng or random.Random()
        self.config = config
        self.making: set[Id] = set()
        self.tasks: set[asyncio.Task[Work | None]] = set()

    def make(
        self, npc: Npc, wall: Id | None = None, intention: Intention | None = None
    ) -> asyncio.Task[Work | None] | None:
        """Start `npc` writing a piece, painting a mural on `wall`, or painting for the gallery:
        a painter, or a muralist given anything but a wall. Not if they don't make that, are
        making something already, or there's no LLM. Doesn't block. The task stores the work
        and the artist's memory of making it and returns the work, or None if it fails. With
        the `intention` they're keeping, its idea leads the prompt."""
        llm, craft = self.llm(), npc.craft
        if llm is None or craft is None or npc.id in self.making:
            return None
        now = self.clock.now
        making: Coroutine[Any, Any, Work | None]
        if craft.medium is Medium.WRITING:
            making = self._write(llm, npc, craft, now, intention)
        elif craft.medium is Medium.MURAL and wall in self.walls:
            making = self._paint(llm, npc, craft, self.walls[wall], now, intention)
        elif self.hang is not None:
            making = self._canvas(llm, npc, craft, self.hang, now, intention)
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
        """`npc`'s strongest memories by salience × recency, others' works weighed down by
        `others_works` and their own left out, and their latest works."""
        config = self.config
        theirs = self.works.by(npc.id)
        own = {work.id for work in theirs}
        recalled = self.memory.recall(
            npc.id, now, k=config.recalled + len(own), half_life=config.half_life
        )
        half_life = config.half_life.total_seconds()

        def pull(memory: Memory) -> float:
            weight = config.others_works if memory.work_id else 1.0
            age = (now - memory.timestamp).total_seconds()
            return memory.salience * recency(age, half_life) * weight

        mine = [m for m in recalled if m.work_id not in own]
        return sorted(mine, key=pull, reverse=True)[: config.memories], theirs[: config.past_works]

    def commission(
        self, npc: Npc, medium: Medium, now: datetime, intention: Intention | None = None
    ) -> Commission:
        memories, past = self.on_mind(npc, now)
        village = self.works.newest(self.config.village_works, besides=npc.id)
        seed = draw_seed(medium, self.rng, self.config)
        told = idea(intention, self.npcs)
        return Commission(memories, past, village, seed, told, self.npcs)

    async def _write(
        self, llm: LLMClient, npc: Npc, craft: Craft, now: datetime, intention: Intention | None
    ) -> Work | None:
        commission = self.commission(npc, Medium.WRITING, now, intention)
        ask = prompt(craft, commission, self.config)
        reply = await self._ask(llm, npc, craft, ask, Reply, "work")
        if reply is None:
            return None
        key = uuid.uuid4().hex[:8]
        work = self._work(
            npc,
            craft,
            reply,
            reply.text,
            commission.memories,
            now,
            key,
            Medium.WRITING,
            intention=intention,
        )
        self.works.add(work)
        self.memory.add(remember(npc, work, self.config))
        logger.info("%s wrote %r (%s): %s", npc.id, work.title, commission.seed, work.statement)
        return work

    async def _paint(
        self,
        llm: LLMClient,
        npc: Npc,
        craft: Craft,
        wall: MuralWall,
        now: datetime,
        intention: Intention | None,
    ) -> Work | None:
        commission = self.commission(npc, Medium.MURAL, now, intention)
        showing = self.works.showing().get(wall.id)
        on_it = "It's blank."
        if showing:
            who = "you" if showing.artist == npc.id else name_of(self.npcs, showing.artist)
            on_it = (
                f'You\'re painting over {self._whose(npc, showing)} "{showing.title}", of which '
                f'{who} said: "{showing.statement}"'
            )
        key = uuid.uuid4().hex[:8]

        def ask(painted: bool) -> str:
            return mural_prompt(craft, commission, wall, on_it, self.config, painted=painted)

        made = await self._picture(llm, npc, craft, Medium.MURAL, ask, canvas(wall), int(key, 16))
        if made is None:
            return None
        reply, svg, png = made
        work = self._work(
            npc,
            craft,
            reply,
            reply.description,
            commission.memories,
            now,
            key,
            Medium.MURAL,
            wall.id,
            intention=intention,
        )
        covered = self.works.paint(work, svg, png)
        over = f' over {self._whose(npc, covered, "my")} "{covered.title}"' if covered else ""
        self.memory.add(remember(npc, work, self.config, over))
        logger.info(
            "%s painted %r on %s (%s): %s",
            npc.id,
            work.title,
            wall.id,
            commission.seed,
            work.statement,
        )
        self.painted(work)
        return work

    async def _canvas(
        self,
        llm: LLMClient,
        npc: Npc,
        craft: Craft,
        hang: Hang,
        now: datetime,
        intention: Intention | None,
    ) -> Work | None:
        commission = self.commission(npc, Medium.PAINTING, now, intention)
        key = uuid.uuid4().hex[:8]

        def ask(painted: bool) -> str:
            return painting_prompt(craft, commission, self.config, painted=painted)

        size = painting_canvas()
        made = await self._picture(llm, npc, craft, Medium.PAINTING, ask, size, int(key, 16))
        if made is None:
            return None
        reply, svg, png = made
        work = self._work(
            npc,
            craft,
            reply,
            reply.description,
            commission.memories,
            now,
            key,
            Medium.PAINTING,
            intention=intention,
        )
        self.works.add(work)
        hang(work, svg, png)
        self.memory.add(remember(npc, work, self.config))
        logger.info(
            "%s painted %r for the gallery (%s): %s",
            npc.id,
            work.title,
            commission.seed,
            work.statement,
        )
        return work

    async def _picture(
        self,
        llm: LLMClient,
        npc: Npc,
        craft: Craft,
        medium: Medium,
        ask: Callable[[bool], str],
        size: tuple[int, int],
        seed: int,
    ) -> tuple[Any, str, bytes] | None:
        """A mural's or painting's reply, SVG and PNG. With a painter, it's painted from a
        description and has no SVG. Without one, or if painting fails, it's drawn as SVG. None if
        a call fails or no SVG will do."""
        on_canvas = medium is Medium.PAINTING
        if self.painter is not None:
            reply = await self._ask(llm, npc, craft, ask(True), PAINTED[medium], medium.value)
            if reply is None:
                return None
            try:
                picture = await self.painter.paint(image_prompt(reply.picture, medium), *size, seed)
            except PaintingFailed as error:
                logger.warning(
                    "%s's %s couldn't be painted, so drawing it: %s", npc.id, medium.value, error
                )
            else:
                png = await asyncio.to_thread(
                    finish, picture, *size, seed=seed, on_canvas=on_canvas
                )
                return reply, "", png
        first = again = ask(False)
        for _ in range(2):
            reply = await self._ask(llm, npc, craft, again, DRAWN[medium], medium.value)
            if reply is None:
                return None
            try:
                svg, png = await self._drawing(reply.svg, *size, seed, on_canvas=on_canvas)
                return reply, svg, png
            except BadSvg as error:
                logger.info("%s's %s won't do: %s", npc.id, medium.value, error)
                again = (
                    f"{first}\n\nYour last try couldn't {GOES_UP[medium]}, because {error}. "
                    "Fix that."
                )
        logger.warning(
            "%s couldn't draw a %s that would %s, so made nothing",
            npc.id,
            medium.value,
            GOES_UP[medium],
        )
        return None

    async def _drawing(
        self, svg: str, width: int, height: int, seed: int, *, on_canvas: bool = False
    ) -> tuple[str, bytes]:
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
            draw,
            svg,
            width,
            height,
            seed=seed,
            timeout=config.render_timeout,
            memory=config.render_memory * 2**20,
            on_canvas=on_canvas,
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
        reply: Any,
        text: str,
        memories: Sequence[Memory],
        now: datetime,
        key: str,
        medium: Medium,
        wall: Id | None = None,
        *,
        intention: Intention | None = None,
    ) -> Work:
        """Inspired by the conversation the `intention` came from, first, and the memories it
        says."""
        sources = [source(memories[n - 1]) for n in reply.inspired_by if 1 <= n <= len(memories)]
        if intention is not None:
            sources.insert(0, intention.conversation_id)
        return Work(
            id=f"{npc.id}-{key}",
            artist=npc.id,
            medium=medium,
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
