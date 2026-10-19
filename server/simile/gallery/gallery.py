import logging
import math
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime

from simile.behaviour import MuralSpot, Places, WallPicker
from simile.gallery.config import DEFAULT_CONFIG, GalleryConfig
from simile.gallery.store import FrameKey, GalleryStore
from simile.protocol import Artist, Frame, Painting, PaintingsMessage
from simile.schema import VILLAGE_MAP, Id, Interactable, InteractableKind, Medium, Npc, Work
from simile.sim import Clock
from simile.works.reading import name_of
from simile.works.store import WorksStore
from simile.world.map import TownMap

logger = logging.getLogger(__name__)


def frames_of(maps: Mapping[str, TownMap]) -> list[Interactable]:
    """Every painting interactable, those nearest their room's door first, so a new gallery
    fills from the entrance."""

    def from_door(frame: Interactable) -> float:
        doors = [door.inside for door in maps[frame.map].doors if door.inside.map == frame.map]
        stand = frame.stand[0]
        return min((math.dist((d.x, d.y), (stand.x, stand.y)) for d in doors), default=0.0)

    found = [
        item
        for town in maps.values()
        for item in town.interactables
        if item.kind is InteractableKind.PAINTING and item.map == town.id
    ]
    return sorted(found, key=from_door)


def key(frame: Interactable) -> FrameKey:
    return frame.map, frame.id


def nothing_hung() -> None:
    return None


class Gallery:
    """The gallery's frames and the paintings in them: one each, a new one replacing the one hung
    longest ago."""

    def __init__(
        self,
        frames: Sequence[Interactable],
        store: GalleryStore,
        works: WorksStore,
        clock: Clock,
        npcs: Mapping[Id, Npc],
        *,
        hung: Callable[[], None] = nothing_hung,
    ) -> None:
        """`hung()` is called after each new painting goes up."""
        self.frames = list(frames)
        self.store = store
        self.works = works
        self.clock = clock
        self.npcs = npcs
        self.hung = hung

    def hang(self, work: Work, svg: str, png: bytes, when: datetime | None = None) -> FrameKey:
        """Maker's `hang`, hung `when`, or now."""
        frames = [key(f) for f in self.frames]
        frame = self.store.hang(work.id, svg, png, frames, when or self.clock.now)
        logger.info("Hung %s's %r in %s on %s", work.artist, work.title, frame[1], frame[0])
        self.hung()
        return frame

    def showing(self) -> dict[FrameKey, Work]:
        """The painting in each frame that has one."""
        hanging = self.store.hanging()
        works = {key: self.works.get(work_id) for key, work_id in hanging.items()}
        return {key: work for key, work in works.items() if work is not None}

    def message(self) -> PaintingsMessage:
        showing = self.showing()
        return PaintingsMessage(
            frames=[
                Frame(id=frame.id, map=frame.map, painting=self._painting(showing.get(key(frame))))
                for frame in self.frames
            ]
        )

    def _painting(self, work: Work | None) -> Painting | None:
        if work is None:
            return None
        return Painting(
            work_id=work.id,
            title=work.title,
            artist=Artist(id=work.artist, name=name_of(self.npcs, work.artist)),
            statement=work.statement,
            image=f"/api/gallery/{work.id}.png",
        )


def taking_turns(
    pick: WallPicker, works: WorksStore, places: Places, config: GalleryConfig = DEFAULT_CONFIG
) -> WallPicker:
    """B1's `mural_wall` around `pick`: a muralist paints for the gallery after every
    `murals_per_canvas` murals in a row, and whenever no wall is worth painting. Then it names
    their home, where they paint a canvas."""

    def home(npc: Npc) -> MuralSpot | None:
        location = places.location(npc.home)
        return MuralSpot(npc.home, location.entry) if location.map == VILLAGE_MAP else None

    def mural_wall(npc: Npc) -> MuralSpot | None:
        latest = works.by(npc.id, config.murals_per_canvas)
        murals = [work for work in latest if work.medium is Medium.MURAL]
        if latest and len(murals) == config.murals_per_canvas:
            return home(npc) or pick(npc)
        return pick(npc) or home(npc)

    return mural_wall
