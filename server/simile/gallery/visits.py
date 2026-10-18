import asyncio
import logging
import math
import random
import sys
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta

from simile.behaviour import Activity, GoalChosen, Mind
from simile.gallery.config import DEFAULT_CONFIG, GalleryConfig
from simile.gallery.gallery import Gallery, key
from simile.gallery.store import FrameKey
from simile.llm import LLMClient, StructuredOutputError
from simile.memory import MemoryStore
from simile.news.reactions import system_prompt
from simile.schema import PLAYER_ID, Id, Interactable, MapTile, Memory, MemoryKind, Npc, Work
from simile.sim import Clock
from simile.social import as_of, describe, meet
from simile.works.reading import Reaction, how_it_lands, name_of
from simile.world.movement import Movement, Outcome, Point, Walk, spot_of

logger = logging.getLogger(__name__)


def painting_prompt(painting: Work, artist: str, feeling: str) -> str:
    return (
        f"You're at the village gallery, looking at a painting by {artist}, who makes "
        f'{painting.form}.\n\nIt\'s called "{painting.title}". {painting.text}\n\n'
        f"{artist} says of it: {painting.statement}\n\n{feeling}\n\n{how_it_lands(artist)}"
    )


def standing_at(frame: Interactable, position: Point) -> bool:
    spot = spot_of(position)
    return spot.map == frame.map and any((t.x, t.y) == (spot.x, spot.y) for t in frame.stand)


class Visitors:
    """Residents visiting the gallery walk from painting to painting, those they haven't seen
    first, and say how each new one lands in one LLM call. The player remembers each painting they
    stand at. Tick it on the sim loop, and give it every `GoalChosen`."""

    def __init__(
        self,
        gallery: Gallery,
        memory: MemoryStore,
        clock: Clock,
        llm: Callable[[], LLMClient | None],
        npcs: Mapping[Id, Npc],
        minds: Mapping[Id, Mind],
        movement: Movement,
        *,
        config: GalleryConfig = DEFAULT_CONFIG,
        seed: int | None = None,
    ) -> None:
        """`minds` are B1's, read to find who's visiting and staying put."""
        self.gallery = gallery
        self.memory = memory
        self.clock = clock
        self.llm = llm
        self.npcs = npcs
        self.minds = minds
        self.movement = movement
        self.config = config
        self.rng = random.Random(seed)
        self.seen: dict[Id, set[str]] = {}
        self.later: dict[tuple[Id, str], datetime] = {}
        """When a visitor whose look at a painting failed can look again, by their id and its."""
        self.walks: dict[Id, tuple[Walk, Interactable]] = {}
        self.looking: dict[Id, tuple[FrameKey, datetime]] = {}
        """The frame each visitor is in front of, and until when."""
        self.tasks: set[asyncio.Task[None]] = set()
        self._elapsed = 0.0

    def tick(self, dt: float) -> None:
        self._elapsed += dt
        if self._elapsed >= self.config.look_every - 1e-9:
            self._elapsed = 0.0
            self.look()

    def on_goal(self, event: GoalChosen) -> None:
        """Stops showing them round once they're off to do something else, or talking."""
        self.looking.pop(event.npc, None)
        walking = self.walks.pop(event.npc, None)
        if walking is not None and not walking[0].done:
            self.movement.stop(event.npc)

    def look(self) -> None:
        showing = self.gallery.showing()
        hung = [
            (frame, showing[key(frame)]) for frame in self.gallery.frames if key(frame) in showing
        ]
        if not hung:
            return
        positions = self.movement.entities()
        if (player := positions.get(PLAYER_ID)) is not None:
            for frame, painting in hung:
                if standing_at(frame, player) and painting.id not in self._seen_by(PLAYER_ID):
                    self._seen_by(PLAYER_ID).add(painting.id)
                    self.memory.add(self._player_saw(painting))
        for who, mind in self.minds.items():
            position = positions.get(who)
            if position is None or not self._staying(mind):
                continue
            if here := [(frame, painting) for frame, painting in hung if frame.map == position.map]:
                self._show_round(who, position, here)

    async def stop(self) -> None:
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def _staying(self, mind: Mind) -> bool:
        return mind.goal.activity is Activity.GALLERY and mind.walk is None and not mind.paused

    def _show_round(self, who: Id, position: Point, hung: list[tuple[Interactable, Work]]) -> None:
        if who in self.walks:
            walk, frame = self.walks[who]
            if not walk.done:
                return
            del self.walks[who]
            if walk.outcome is Outcome.ARRIVED:
                self._arrive(who, frame, {key(f): p for f, p in hung}.get(key(frame)))
                return
        at = self.looking.get(who)
        if at is not None and at[1] > self.clock.now:
            return
        frame = self._next(who, position, hung, at[0] if at else None)
        stand = self.rng.choice(frame.stand)
        walk = self.movement.walk_to(who, MapTile(map=frame.map, x=stand.x, y=stand.y))
        self.walks[who] = (walk, frame)

    def _next(
        self,
        who: Id,
        position: Point,
        hung: list[tuple[Interactable, Work]],
        last: FrameKey | None,
    ) -> Interactable:
        """The nearest painting they haven't seen, or any but the one they've just looked at."""
        unseen = [frame for frame, painting in hung if self._new_to(who, painting)]
        if unseen:
            stand = position.x, position.y
            return min(unseen, key=lambda f: math.dist(stand, (f.stand[0].x, f.stand[0].y)))
        others = [frame for frame, _ in hung if key(frame) != last]
        return self.rng.choice(others or [frame for frame, _ in hung])

    def _arrive(self, who: Id, frame: Interactable, painting: Work | None) -> None:
        minutes = self.rng.uniform(*self.config.linger)
        self.looking[who] = (key(frame), self.clock.now + timedelta(minutes=minutes))
        if painting is None or not self._new_to(who, painting) or (llm := self.llm()) is None:
            return
        self._seen_by(who).add(painting.id)
        task = asyncio.get_running_loop().create_task(
            self._look_at(llm, self.npcs[who], painting, self.clock.now)
        )
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    def _new_to(self, who: Id, painting: Work) -> bool:
        """Whether it's someone else's that they haven't seen, and haven't just failed to."""
        return (
            painting.artist != who
            and painting.id not in self._seen_by(who)
            and self.later.get((who, painting.id), self.clock.now) <= self.clock.now
        )

    def _seen_by(self, who: Id) -> set[str]:
        if who not in self.seen:
            memories = self.memory.recall(who, self.clock.now, kind=MemoryKind.WORK, k=sys.maxsize)
            self.seen[who] = {memory.work_id for memory in memories if memory.work_id}
        return self.seen[who]

    def _player_saw(self, painting: Work) -> Memory:
        return Memory(
            owner=PLAYER_ID,
            kind=MemoryKind.WORK,
            content=f"I saw {name_of(self.npcs, painting.artist)}'s painting "
            f'"{painting.title}" at the gallery.',
            salience=self.config.player_salience,
            valence=0,
            timestamp=self.clock.now,
            about=[painting.artist],
            topics=painting.tags[: self.config.topics],
            work_id=painting.id,
        )

    async def _look_at(self, llm: LLMClient, npc: Npc, painting: Work, now: datetime) -> None:
        try:
            await self._react(llm, npc, painting, now)
        except StructuredOutputError:
            logger.warning("%s couldn't rate %r", npc.id, painting.title)
        except Exception:
            logger.warning("%s couldn't look at %r", npc.id, painting.title, exc_info=True)
            self.seen[npc.id].discard(painting.id)
            self.later[(npc.id, painting.id)] = self.clock.now + self.config.look_again

    async def _react(self, llm: LLMClient, npc: Npc, painting: Work, now: datetime) -> None:
        artist = name_of(self.npcs, painting.artist)
        rel = self.memory.relationship(npc.id, painting.artist) or meet(npc, painting.artist)
        reaction = await llm.structured(
            painting_prompt(painting, artist, describe(as_of(rel, now), artist)),
            Reaction,
            system=system_prompt(npc),
            model=self.config.reaction_model,
            purpose="painting-reaction",
            priority=self.config.priority,
        )
        self.memory.add(
            Memory(
                owner=npc.id,
                kind=MemoryKind.WORK,
                content=f'At the gallery I looked at {artist}\'s painting "{painting.title}". '
                f"{reaction.take.strip()}",
                salience=reaction.intensity,
                valence=reaction.valence,
                timestamp=now,
                about=[painting.artist],
                topics=painting.tags[: self.config.topics],
                work_id=painting.id,
            )
        )
        logger.info(
            "%s looked at %s's %r: valence %.2f, intensity %.2f. %s",
            npc.id,
            painting.artist,
            painting.title,
            reaction.valence,
            reaction.intensity,
            reaction.take,
        )
