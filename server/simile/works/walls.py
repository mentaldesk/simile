import math
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime

from simile.behaviour import MuralSpot
from simile.behaviour.scoring import affinity
from simile.memory import MemoryStore
from simile.protocol import Artist, Mural, MuralsMessage, Wall
from simile.schema import CoreValue, Id, MapTile, Npc, Work
from simile.sim import Clock
from simile.social import as_of, meet
from simile.works.config import DEFAULT_CONFIG, WorksConfig
from simile.works.reading import name_of
from simile.works.store import WorksStore
from simile.world.map import MuralWall
from simile.world.movement import Point


def wall_name(wall: Id) -> str:
    return f"the {wall.replace('_', ' ')} wall"


def boldness(npc: Npc) -> float:
    """How ready they are to paint over someone else's work, 0 to 1, from their values."""
    values = npc.values
    return (
        2 - values[CoreValue.TRADITION] - values[CoreValue.OBEDIENCE] + values[CoreValue.FREEDOM]
    ) / 3


def readiness(
    painter: Npc, mural: Work, fondness: float, now: datetime, config: WorksConfig = DEFAULT_CONFIG
) -> float | None:
    """How ready `painter` is to paint over `mural`, given their B1 affinity for its artist, or
    None if they never would, or not while it's `fresh`."""
    if now - mural.created < config.fresh:
        return None
    age = config.age_weight * min((now - mural.created) / config.mural_age, 1.0)
    if mural.artist == painter.id:
        return age + config.own_mural
    bold = boldness(painter)
    if fondness >= config.friend and bold < config.friend_boldness:
        return None
    return age + config.boldness_weight * (bold - 0.5) - config.fondness_weight * fondness


def stand(wall: MuralWall) -> MapTile:
    """Where its painter stands, on its map."""
    if wall.map is None:
        raise ValueError(f"{wall.id} isn't on a map")
    return MapTile(map=wall.map, x=wall.stand.x, y=wall.stand.y)


def away(here: Point, wall: MuralWall) -> float:
    """How far it is to the wall's painter's tile, on the same map, or else infinitely far."""
    if wall.map is not None and wall.map != here.map:
        return math.inf
    return math.dist(here, (wall.stand.x, wall.stand.y))


def nobody_painting() -> dict[Id, Id]:
    return {}


def unpromised(npc: Id) -> Id | None:
    return None


class Walls:
    """The walls that take murals: B1's `mural_wall` hook, and the `murals` message."""

    def __init__(
        self,
        walls: Sequence[MuralWall],
        works: WorksStore,
        memory: MemoryStore,
        clock: Clock,
        npcs: Mapping[Id, Npc],
        *,
        positions: Callable[[], Mapping[Id, Point]] = dict,
        painting: Callable[[], Mapping[Id, Id]] = nobody_painting,
        promised: Callable[[Id], Id | None] = unpromised,
        config: WorksConfig = DEFAULT_CONFIG,
    ) -> None:
        """`painting()` is the wall each muralist is off to paint or painting now, by their id,
        and `promised(npc)` the wall they've said they'll paint, if any."""
        self.walls = walls
        self.works = works
        self.memory = memory
        self.clock = clock
        self.npcs = npcs
        self.positions = positions
        self.painting = painting
        self.promised = promised
        self.config = config

    def pick(self, npc: Npc) -> MuralSpot | None:
        """The wall they said they'd paint, if it's blank or ready enough, or else the nearest
        blank wall, or else the one `npc` is readiest to paint over, if any is ready enough.
        Nobody picks a wall someone else is painting."""
        busy = {wall for who, wall in self.painting().items() if who != npc.id}
        free = [wall for wall in self.walls if wall.id not in busy]
        showing = self.works.showing()
        said = next((wall for wall in free if wall.id == self.promised(npc.id)), None)
        if said is not None and self._ready(npc, showing.get(said.id)):
            return MuralSpot(said.id, stand(said))
        if blank := [wall for wall in free if wall.id not in showing]:
            if (here := self.positions().get(npc.id)) is not None:
                blank.sort(key=lambda wall: away(here, wall))
            return MuralSpot(blank[0].id, stand(blank[0]))
        ready = [
            (score, wall)
            for wall in free
            if (score := self.readiness(npc, showing[wall.id])) is not None
        ]
        best = max(ready, key=lambda pair: pair[0], default=None)
        if best is None or best[0] < self.config.min_readiness:
            return None
        return MuralSpot(best[1].id, stand(best[1]))

    def readiness(self, painter: Npc, mural: Work) -> float | None:
        fondness = 0.0
        if mural.artist != painter.id:
            rel = self.memory.relationship(painter.id, mural.artist) or meet(painter, mural.artist)
            fondness = affinity(as_of(rel, self.clock.now))
        return readiness(painter, mural, fondness, self.clock.now, self.config)

    def _ready(self, painter: Npc, mural: Work | None) -> bool:
        """Whether a wall showing `mural`, or blank, is ready enough for `painter` to paint."""
        if mural is None:
            return True
        score = self.readiness(painter, mural)
        return score is not None and score >= self.config.min_readiness

    def message(self) -> MuralsMessage:
        showing = self.works.showing()
        return MuralsMessage(
            walls=[
                Wall(
                    id=wall.id,
                    x=wall.x,
                    y=wall.y,
                    width=wall.width,
                    face=wall.face,
                    bottom=wall.bottom,
                    top=wall.top,
                    mural=self._mural(showing[wall.id]) if wall.id in showing else None,
                    **({"map": wall.map} if wall.map else {}),
                )
                for wall in self.walls
            ]
        )

    def _mural(self, work: Work) -> Mural:
        return Mural(
            work_id=work.id,
            title=work.title,
            artist=Artist(id=work.artist, name=name_of(self.npcs, work.artist)),
            statement=work.statement,
            image=f"/api/works/{work.id}.png",
        )
