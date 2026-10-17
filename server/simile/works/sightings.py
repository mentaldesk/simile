import asyncio
import logging
import math
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime

from simile.llm import LLMClient, StructuredOutputError
from simile.memory import MemoryStore
from simile.news.reactions import system_prompt
from simile.schema import PLAYER_ID, Id, Memory, MemoryKind, Npc, Work
from simile.sim import Clock
from simile.social import as_of, describe, meet
from simile.works.config import DEFAULT_CONFIG, WorksConfig
from simile.works.reading import Reaction, how_it_lands, name_of
from simile.works.store import WorksStore
from simile.works.walls import wall_name
from simile.world.map import MuralWall
from simile.world.movement import Point

logger = logging.getLogger(__name__)


def distance_in_front(wall: MuralWall, position: Point) -> float | None:
    """How far someone standing at `position` is from the wall's face, or None behind it. As the
    client's `distanceInFront`, from the middle of their tile."""
    x, y = position.x + 0.5, position.y + 0.5
    out, along, start = (
        (y - (wall.y + 1), x, wall.x) if wall.face == "south" else (x - (wall.x + 1), y, wall.y)
    )
    if out <= 0:
        return None
    return math.hypot(out, max(start - along, 0, along - (start + wall.width)))


def mural_prompt(mural: Work, artist: str, wall: str, feeling: str, yours: Work | None) -> str:
    over = f' It\'s painted over your own mural there, "{yours.title}".' if yours else ""
    return (
        f"You've just walked past a mural on {wall}, by {artist}, who paints {mural.form}.{over}"
        f'\n\nIt\'s called "{mural.title}". {mural.text}\n\n'
        f"{artist} says of it: {mural.statement}\n\n{feeling}\n\n{how_it_lands(artist)}"
    )


class Passers:
    """Residents and the player who come within reach of a mural they haven't seen. A resident
    says how it lands in one LLM call, and the player just remembers it. Tick it on the sim loop."""

    def __init__(
        self,
        works: WorksStore,
        memory: MemoryStore,
        clock: Clock,
        llm: Callable[[], LLMClient | None],
        npcs: Mapping[Id, Npc],
        walls: Sequence[MuralWall],
        positions: Callable[[], Mapping[Id, Point]],
        *,
        config: WorksConfig = DEFAULT_CONFIG,
    ) -> None:
        self.works = works
        self.memory = memory
        self.clock = clock
        self.llm = llm
        self.npcs = npcs
        self.walls = walls
        self.positions = positions
        self.config = config
        self.seen: dict[Id, set[str]] = {}
        self.later: dict[tuple[Id, str], datetime] = {}
        """When a resident whose look at a mural failed can look again, by their id and its."""
        self.tasks: set[asyncio.Task[None]] = set()
        self._elapsed = 0.0

    def tick(self, dt: float) -> None:
        self._elapsed += dt
        if self._elapsed >= self.config.look_every - 1e-9:
            self._elapsed = 0.0
            self.look()

    def look(self) -> None:
        showing = self.works.showing()
        painted = [(wall, showing[wall.id]) for wall in self.walls if wall.id in showing]
        if not painted:
            return
        for who, position in self.positions().items():
            if who != PLAYER_ID and who not in self.npcs:
                continue
            for wall, mural in painted:
                distance = distance_in_front(wall, position)
                if distance is None or distance > self.config.reach or mural.artist == who:
                    continue
                if mural.id in self._seen_by(who):
                    continue
                if self.later.get((who, mural.id), self.clock.now) <= self.clock.now:
                    self._see(who, wall, mural)

    async def stop(self) -> None:
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def _see(self, who: Id, wall: MuralWall, mural: Work) -> None:
        if who == PLAYER_ID:
            self._seen_by(who).add(mural.id)
            self.memory.add(self._player_saw(wall, mural))
            return
        llm = self.llm()
        if llm is None:
            return
        self._seen_by(who).add(mural.id)
        task = asyncio.get_running_loop().create_task(
            self._look_at(llm, self.npcs[who], wall, mural, self.clock.now)
        )
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    def _seen_by(self, who: Id) -> set[str]:
        if who not in self.seen:
            memories = self.memory.recall(who, self.clock.now, kind=MemoryKind.WORK, k=sys.maxsize)
            self.seen[who] = {memory.work_id for memory in memories if memory.work_id}
        return self.seen[who]

    def _player_saw(self, wall: MuralWall, mural: Work) -> Memory:
        return Memory(
            owner=PLAYER_ID,
            kind=MemoryKind.WORK,
            content=f'I saw {name_of(self.npcs, mural.artist)}\'s mural "{mural.title}" on '
            f"{wall_name(wall.id)}.",
            salience=self.config.player_salience,
            valence=0,
            timestamp=self.clock.now,
            about=[mural.artist],
            topics=mural.tags[: self.config.topics],
            work_id=mural.id,
        )

    async def _look_at(
        self, llm: LLMClient, npc: Npc, wall: MuralWall, mural: Work, now: datetime
    ) -> None:
        try:
            await self._react(llm, npc, wall, mural, now)
        except StructuredOutputError:
            logger.warning("%s couldn't rate %r", npc.id, mural.title)
        except Exception:
            logger.warning("%s couldn't look at %r", npc.id, mural.title, exc_info=True)
            self.seen[npc.id].discard(mural.id)
            self.later[(npc.id, mural.id)] = self.clock.now + self.config.look_again

    async def _react(
        self, llm: LLMClient, npc: Npc, wall: MuralWall, mural: Work, now: datetime
    ) -> None:
        artist = name_of(self.npcs, mural.artist)
        rel = self.memory.relationship(npc.id, mural.artist) or meet(npc, mural.artist)
        feeling = describe(as_of(rel, now), artist)
        covered = self.works.covered(mural.id)
        yours = covered if covered is not None and covered.artist == npc.id else None
        reaction = await llm.structured(
            mural_prompt(mural, artist, wall_name(wall.id), feeling, yours),
            Reaction,
            system=system_prompt(npc),
            model=self.config.reaction_model,
            purpose="mural-reaction",
            priority=self.config.priority,
        )
        saw = (
            f'{artist} has painted "{mural.title}" over my mural "{yours.title}" on '
            if yours
            else f'I saw {artist}\'s mural "{mural.title}" on '
        )
        salience = max(reaction.intensity, self.config.painted_over_salience if yours else 0)
        self.memory.add(
            Memory(
                owner=npc.id,
                kind=MemoryKind.WORK,
                content=f"{saw}{wall_name(wall.id)}. {reaction.take.strip()}",
                salience=salience,
                valence=reaction.valence,
                timestamp=now,
                about=[mural.artist],
                topics=mural.tags[: self.config.topics],
                work_id=mural.id,
            )
        )
        logger.info(
            "%s saw %s's %r: valence %.2f, intensity %.2f. %s",
            npc.id,
            mural.artist,
            mural.title,
            reaction.valence,
            reaction.intensity,
            reaction.take,
        )
