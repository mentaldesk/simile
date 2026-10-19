import asyncio
import logging
import tempfile
from collections import Counter
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from pydantic import TypeAdapter

from simile.llm import LLMClient
from simile.memory import MemoryStore
from simile.schema import CoreValue, Id, Medium, Npc, Work
from simile.sim import Clock
from simile.works.config import DEFAULT_CONFIG, WorksConfig
from simile.works.maker import Maker, remember
from simile.works.store import WorksStore
from simile.world.map import MuralWall

logger = logging.getLogger(__name__)

STARTERS = Path(__file__).resolve().parents[3] / "content" / "works"
INDEX = "works.json"
SEEDED = "starters"
WORKS = TypeAdapter(list[Work])

type Hanging = Callable[[Work, str, bytes, datetime], object]
"""Hangs a painting in the gallery, given its SVG and PNG and when it went up."""


@dataclass(frozen=True)
class Slot:
    """A starter work: who makes it, in what, and for a mural, on which wall."""

    artist: Id
    medium: Medium
    wall: Id | None = None


PLAN = (
    Slot("kofi", Medium.MURAL, "tower"),
    Slot("desmond", Medium.WRITING),
    Slot("priya", Medium.PAINTING),
    Slot("ingrid", Medium.MURAL, "garden_flats"),
    Slot("mirela", Medium.WRITING),
    Slot("tobias", Medium.PAINTING),
    Slot("odalys", Medium.MURAL, "daily_grind"),
    Slot("lachlan", Medium.WRITING),
    Slot("ingrid", Medium.PAINTING),
    Slot("henrietta", Medium.WRITING),
    Slot("priya", Medium.PAINTING),
    Slot("marguerite", Medium.WRITING),
    Slot("kofi", Medium.MURAL, "corner_shop"),
    Slot("tobias", Medium.PAINTING),
    Slot("raymond", Medium.WRITING),
)
"""Today's village: a mural on four of the five walls, a piece from each writer, and five
paintings, in the order they're made, so an artist's second work sees their first."""


@dataclass(frozen=True)
class Starter:
    work: Work
    svg: str | None = None
    png: bytes | None = None


def load(path: Path = STARTERS) -> list[Starter]:
    """The starter works in `path`, oldest first, with the pictures of murals and paintings."""
    index = path / INDEX
    if not index.is_file():
        return []
    starters = []
    for work in WORKS.validate_json(index.read_bytes()):
        if work.medium is Medium.WRITING:
            starters.append(Starter(work))
        else:
            svg, png = path / f"{work.id}.svg", path / f"{work.id}.png"
            starters.append(Starter(work, svg.read_text(encoding="utf-8"), png.read_bytes()))
    return starters


def save(starters: Sequence[Starter], path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for starter in starters:
        if starter.svg is not None and starter.png is not None:
            (path / f"{starter.work.id}.svg").write_text(starter.svg, encoding="utf-8")
            (path / f"{starter.work.id}.png").write_bytes(starter.png)
    works = [starter.work for starter in starters]
    (path / INDEX).write_bytes(WORKS.dump_json(works, indent=2) + b"\n")


def seed(
    works: WorksStore,
    memory: MemoryStore,
    npcs: Mapping[Id, Npc],
    now: datetime,
    *,
    hang: Hanging | None = None,
    path: Path = STARTERS,
    config: WorksConfig = DEFAULT_CONFIG,
) -> list[Work]:
    """Store the starter works as if made before the save's first work, or before `now` if it
    has none, the newest `starters_newest` before it, give each artist their memory of making
    theirs, put the murals on the walls that are still blank and hang the paintings. Only into a
    store that's never had them, so never twice."""
    starters = load(path)
    if not starters or not works.first_time(SEEDED, now):
        return []
    first = works.oldest()
    before = min(now, first.created) if first else now
    shift = before - config.starters_newest - max(starter.work.created for starter in starters)
    painted = set(works.showing())
    seeded = []
    for starter in starters:
        work = starter.work.model_copy(update={"created": starter.work.created + shift})
        svg, png = starter.svg or "", starter.png or b""
        if work.medium is Medium.MURAL:
            if work.wall in painted:
                continue
            works.paint(work, svg, png)
        else:
            works.add(work)
            if work.medium is Medium.PAINTING and hang is not None:
                hang(work, svg, png, work.created)
        if (npc := npcs.get(work.artist)) is not None:
            memory.add(remember(npc, work, config))
        seeded.append(work)
    return seeded


def commission(
    maker: Maker,
    works: WorksStore,
    npcs: Sequence[Npc],
    walls: Sequence[MuralWall],
    now: datetime,
    config: WorksConfig = DEFAULT_CONFIG,
) -> list[asyncio.Task[Work | None]]:
    """A new world's starter works: up to `starters` residents with a craft, the most creative
    first, start making one each through `maker`, muralists on the blank walls in turn and then
    for the gallery. Only into a store with no works that's never had them, so never twice."""
    if not works.empty() or not works.first_time(SEEDED, now):
        return []
    crafters = [npc for npc in npcs if npc.craft is not None]
    crafters.sort(key=lambda npc: -npc.values[CoreValue.CREATIVITY])
    blank = [wall.id for wall in walls]
    tasks = []
    for npc in crafters[: config.starters]:
        assert npc.craft is not None
        wall = blank.pop(0) if npc.craft.medium is Medium.MURAL and blank else None
        if (task := maker.make(npc, wall)) is not None:
            tasks.append(task)
    return tasks


class Stopped(Exception):
    """A starter work couldn't be made."""

    def __init__(self, slot: Slot, made: list[Starter]) -> None:
        super().__init__(f"{slot.artist} couldn't make their {slot.medium.value}")
        self.slot = slot
        self.made = made


def missing(plan: Sequence[Slot], made: Collection[Work]) -> list[Slot]:
    """The slots of `plan` that no work in `made` fills yet."""
    have = Counter((work.artist, work.medium, work.wall) for work in made)
    left = []
    for slot in plan:
        if have[(slot.artist, slot.medium, slot.wall)] > 0:
            have[(slot.artist, slot.medium, slot.wall)] -= 1
        else:
            left.append(slot)
    return left


async def make(
    llm: LLMClient,
    npcs: Mapping[Id, Npc],
    walls: Sequence[MuralWall],
    out: Path,
    *,
    start: datetime,
    every: timedelta = timedelta(hours=5),
    plan: Sequence[Slot] | None = None,
    config: WorksConfig = DEFAULT_CONFIG,
) -> list[Starter]:
    """Make the slots of `plan`, by default `PLAN`, that `out` doesn't have yet, one at a time
    with the usual Maker, `every` apart from `start`, saving each to `out` as it's made.
    `Stopped` at the first that fails, with those made so far saved."""
    made = load(out)
    pictures: dict[str, tuple[str, bytes]] = {}

    def hang(work: Work, svg: str, png: bytes) -> None:
        pictures[work.id] = (svg, png)

    with tempfile.TemporaryDirectory() as scratch:
        db = Path(scratch) / "starters.db"
        with MemoryStore(db) as memory, WorksStore(db) as works:
            for starter in made:
                if starter.work.medium is Medium.MURAL:
                    works.paint(starter.work, starter.svg or "", starter.png or b"")
                else:
                    works.add(starter.work)
            clock = Clock(start + every * len(made))
            maker = Maker(
                works, memory, clock, lambda: llm, walls=walls, npcs=npcs, hang=hang, config=config
            )
            for slot in missing(PLAN if plan is None else plan, [s.work for s in made]):
                task = maker.make(npcs[slot.artist], slot.wall)
                work = await task if task is not None else None
                if work is None or work.medium is not slot.medium:
                    raise Stopped(slot, made)
                if work.medium is Medium.WRITING:
                    starter = Starter(work)
                elif work.medium is Medium.MURAL:
                    starter = Starter(work, works.svg(work.id), works.picture(work.id))
                else:
                    starter = Starter(work, *pictures[work.id])
                made.append(starter)
                save(made, out)
                clock.now += every
    return made
