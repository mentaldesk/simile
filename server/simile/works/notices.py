import asyncio
import logging
import uuid
from collections.abc import Callable, Collection, Mapping
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from simile.llm import LLMClient, StructuredOutputError
from simile.protocol import Artist
from simile.protocol import Notice as Posted
from simile.schema import Id, Npc, Weekday
from simile.sim import Clock
from simile.works.config import DEFAULT_CONFIG, WorksConfig
from simile.works.reading import name_of
from simile.works.store import Notice, WorksStore

logger = logging.getLogger(__name__)


class Draft(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1, description="A few words, as a notice's heading.")
    text: str = Field(min_length=1, description="The notice itself.")


def hours(at: float) -> str:
    return f"{int(at):02d}:{round(at % 1 * 60):02d}"


def when_open(npc: Npc) -> str:
    if not npc.shifts:
        return ""
    times = "; ".join(
        f"{', '.join(day.value.title() for day in shift.days)} {hours(shift.start)} to "
        f"{hours(shift.end)}"
        for shift in npc.shifts
    )
    where = f" at the {npc.workplace.replace('_', ' ')}" if npc.workplace else ""
    return f" You work{where}: {times}."


def system_prompt(npc: Npc) -> str:
    return (
        f"You are {npc.name} ({npc.age}, {npc.occupation}), who lives in a small village of 2026 "
        f"with public news terminals. {npc.persona}\n\nHow you talk: {npc.speaking_style}"
    )


def notice_prompt(npc: Npc, now: datetime, last: Notice | None, words: int) -> str:
    day = Weekday.of(now).value.title()
    before = (
        f'\n\nYour last notice was "{last.title}": {last.text} Put up something else.'
        if last
        else ""
    )
    return (
        f"It's {day}, {now:%H:%M}.{when_open(npc)}\n\n"
        "Put up a short notice on the village board at the news terminals for your business: an "
        "offer, an event or an invitation, in your own voice. Only what you can offer yourself, "
        f"with a day and time if it has one. A heading of a few words, and at most {words} "
        f"words.{before}"
    )


class Noticeboard:
    """Shopkeepers put up a short notice every `notice_every` on the days they work, while
    they're awake, one cheap LLM call each. Notices are kept apart from the works and aren't
    anyone's work. Tick it on the sim loop."""

    def __init__(
        self,
        works: WorksStore,
        clock: Clock,
        llm: Callable[[], LLMClient | None],
        npcs: Mapping[Id, Npc],
        posters: Collection[Id],
        awake: Callable[[Id], bool],
        *,
        config: WorksConfig = DEFAULT_CONFIG,
    ) -> None:
        self.works = works
        self.clock = clock
        self.llm = llm
        self.npcs = npcs
        self.posters = [id for id in posters if id in npcs]
        self.awake = awake
        self.config = config
        self.writing: set[Id] = set()
        self.later: dict[Id, datetime] = {}
        """When a shopkeeper whose last try failed can try again."""
        self.tasks: set[asyncio.Task[Notice | None]] = set()
        self._elapsed = 0.0

    def tick(self, dt: float) -> None:
        self._elapsed += dt
        if self._elapsed >= self.config.notice_check - 1e-9:
            self._elapsed = 0.0
            for poster in self.due():
                self.post(poster)

    def due(self) -> list[Id]:
        """Shopkeepers awake on a day they work whose last notice is `notice_every` old, or who've
        never put one up."""
        now = self.clock.now
        today = Weekday.of(now)
        due = []
        for poster in self.posters:
            if poster in self.writing or not self.awake(poster):
                continue
            if not any(today in shift.days for shift in self.npcs[poster].shifts):
                continue
            if self.later.get(poster, now) > now:
                continue
            last = self.works.last_notice(poster)
            if last is None or now - last.created >= self.config.notice_every:
                due.append(poster)
        return due

    def post(self, poster: Id) -> asyncio.Task[Notice | None] | None:
        llm = self.llm()
        if llm is None or poster in self.writing:
            return None
        self.writing.add(poster)
        task = asyncio.get_running_loop().create_task(self._write(llm, self.npcs[poster]))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        task.add_done_callback(lambda _: self.writing.discard(poster))
        return task

    def board(self) -> list[Posted]:
        """The notices up now, newest first, for the terminals' Village tab."""
        since = self.clock.now - self.config.notice_life
        return [
            Posted(
                notice_id=notice.id,
                title=notice.title,
                text=notice.text,
                poster=Artist(id=notice.poster, name=name_of(self.npcs, notice.poster)),
                created=notice.created,
            )
            for notice in self.works.notices(since, self.config.notices_listed)
        ]

    async def stop(self) -> None:
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _write(self, llm: LLMClient, npc: Npc) -> Notice | None:
        now = self.clock.now
        last = self.works.last_notice(npc.id)
        try:
            draft = await llm.structured(
                notice_prompt(npc, now, last, self.config.notice_words),
                Draft,
                system=system_prompt(npc),
                model=self.config.notice_model,
                purpose="notice",
                priority=self.config.priority,
            )
        except Exception as error:
            fit = isinstance(error, StructuredOutputError)
            logger.warning("%s couldn't write a notice", npc.id, exc_info=not fit)
            self.later[npc.id] = self.clock.now + self.config.look_again
            return None
        notice = Notice(
            id=f"{npc.id}-notice-{uuid.uuid4().hex[:8]}",
            poster=npc.id,
            title=draft.title,
            text=draft.text,
            created=now,
        )
        self.works.post(notice)
        logger.info("%s put up a notice, %r: %s", npc.id, notice.title, notice.text)
        return notice
