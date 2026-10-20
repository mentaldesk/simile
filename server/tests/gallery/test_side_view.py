import asyncio
from datetime import timedelta
from pathlib import Path

from typer.testing import CliRunner

from simile.behaviour import Activity, Goal, Mind
from simile.cli import create_cli
from simile.gallery import Gallery, GalleryStore, Visitors, frames_of
from simile.gallery.visits import standing_at
from simile.llm import FakeProvider, LLMClient
from simile.memory import MemoryStore
from simile.schema import MapTile, MemoryKind
from simile.sim import STEP, Clock, FakeWallClock, World
from simile.works import WorksStore
from simile.works.reading import Reaction
from simile.world.map import STREET_DIR, load_maps
from simile.world.movement import Movement

from .conftest import NOW, RESIDENTS, TOBIAS, painting

STREETS = load_maps(STREET_DIR)
FRAMES = frames_of(STREETS)
runner = CliRunner()
REACTION = Reaction(take="Quiet, and it stays with you.", valence=0.3, intensity=0.5)


def test_frames_fill_the_ground_floor_from_the_door_and_then_each_floor_from_the_lift() -> None:
    floors = [STREETS[frame.map].floor for frame in FRAMES]

    assert floors == [0] * 3 + [1] * 5 + [2] * 5
    assert [frame.id for frame in FRAMES[:4]] == [
        "painting_1",
        "painting_2",
        "painting_3",
        "painting_8",
    ]


def test_a_visitor_takes_the_lift_to_the_paintings_upstairs(
    works: WorksStore, store: GalleryStore, memory: MemoryStore
) -> None:
    world = World(Clock(NOW), FakeWallClock())
    movement = Movement(STREETS, world.bus)
    gallery = Gallery(FRAMES, store, works, world.clock, RESIDENTS)
    for n in range(4):
        work = painting(f"kofi-{n}")
        works.add(work)
        gallery.hang(work, "<svg/>", b"")
    minds = {"tobias": Mind(TOBIAS, {}, 23.0, 6.0, Goal(Activity.GALLERY, "gallery"), NOW)}
    movement.place("tobias", MapTile(map="gallery_floor_0", x=3, y=2))
    llm = LLMClient(FakeProvider([REACTION] * 4))
    visitors = Visitors(gallery, memory, world.clock, lambda: llm, RESIDENTS, minds, movement)
    world.loop.register(movement)
    world.loop.register(visitors)
    stood: list[str] = []

    async def visit() -> None:
        for _ in range(round(30 * 60 / STEP)):
            world.loop.tick()
            await asyncio.sleep(0)
            here = movement.position("tobias")
            frame = next((f.id for f in FRAMES if standing_at(f, here)), None)
            if frame and (not stood or stood[-1] != frame):
                stood.append(frame)
        await asyncio.gather(*visitors.tasks)

    asyncio.run(visit())

    seen = memory.recall("tobias", NOW + timedelta(days=1), kind=MemoryKind.WORK, k=9)
    assert stood[:4] == [frame.id for frame in FRAMES[:4]]
    assert {m.work_id for m in seen} == {f"kofi-{n}" for n in range(4)}


def test_paint_hangs_in_the_frames_of_the_maps_given(database: Path) -> None:
    result = runner.invoke(create_cli(), ["gallery", "paint", "odalys", "--maps", str(STREET_DIR)])

    assert result.exit_code == 0, result.output
    assert result.output.endswith(f"Hung in {FRAMES[0].id} on gallery_floor_0.\n")
