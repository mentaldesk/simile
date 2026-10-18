import asyncio
import math
from datetime import timedelta

from simile.behaviour import DEFAULT_CONFIG, Activity, Behaviour, Goal, GoalChosen, Mind
from simile.gallery import Gallery, GalleryStore, Visitors, frames_of
from simile.gallery.visits import standing_at
from simile.llm import FakeProvider, LLMClient, LLMError, Model
from simile.memory import MemoryStore
from simile.news.reactions import system_prompt
from simile.schema import PLAYER_ID, MapTile, Memory, MemoryKind, Npc
from simile.sim import STEP, Clock, FakeWallClock, World
from simile.works import WorksStore
from simile.works.reading import Reaction
from simile.world.movement import Movement, Point

from .conftest import KOFI, MAPS, NOW, RESIDENTS, painting

FRAMES = frames_of(MAPS)
REACTION = Reaction(take="Loud, but it stays with you.", valence=0.4, intensity=0.6)
TOBIAS, ODALYS = RESIDENTS["tobias"], RESIDENTS["odalys"]
ENTRY = MapTile(map="gallery", x=16, y=12)


class Visit:
    def __init__(
        self,
        works: WorksStore,
        store: GalleryStore,
        memory: MemoryStore,
        llm: LLMClient | None,
        visitors: list[Npc],
    ) -> None:
        self.world = World(Clock(NOW), FakeWallClock())
        self.movement = Movement(MAPS, self.world.bus)
        self.gallery = Gallery(FRAMES, store, works, self.world.clock, RESIDENTS)
        self.minds = {
            npc.id: Mind(npc, {}, 23.0, 6.0, Goal(Activity.GALLERY, "gallery"), NOW)
            for npc in visitors
        }
        for npc in visitors:
            self.movement.place(npc.id, ENTRY)
        self.visitors = Visitors(
            self.gallery,
            memory,
            self.world.clock,
            lambda: llm,
            RESIDENTS,
            self.minds,
            self.movement,
            seed=0,
        )
        self.world.loop.register(self.movement)
        self.world.loop.register(self.visitors)
        self.world.bus.subscribe(GoalChosen, self.visitors.on_goal)

    def hang(self, *works: tuple[str, str]) -> None:
        for work_id, artist in works:
            work = painting(work_id, artist)
            self.gallery.works.add(work)
            self.gallery.hang(work, "<svg/>", b"")

    async def run(self, minutes: float) -> None:
        for _ in range(round(minutes * 60 / STEP)):
            self.world.loop.tick()
            await asyncio.sleep(0)
        await asyncio.gather(*self.visitors.tasks)

    def frame_of(self, who: str) -> str | None:
        here = self.movement.position(who)
        return next((frame.id for frame in FRAMES if standing_at(frame, here)), None)


def looked_at(memory: MemoryStore, owner: str) -> list[Memory]:
    return memory.recall(owner, NOW + timedelta(days=1), kind=MemoryKind.WORK, k=99)


def test_a_visitor_walks_to_the_nearest_painting_and_says_how_it_lands(
    works: WorksStore, store: GalleryStore, memory: MemoryStore
) -> None:
    fake = FakeProvider([REACTION])
    visit = Visit(works, store, memory, LLMClient(fake), [TOBIAS])
    visit.hang(("kofi-1", "kofi"))

    asyncio.run(visit.run(minutes=1))

    assert visit.frame_of("tobias") == FRAMES[0].id
    [request] = fake.requests
    asked = request.messages[-1].content
    assert asked.startswith(
        f"You're at the village gallery, looking at a painting by {KOFI.name}, who makes "
        'political street murals.\n\nIt\'s called "Painting kofi-1". Blue squares on a red field.'
    )
    assert f"{KOFI.name} says of it: What kofi-1 says." in asked
    assert request.system.startswith(system_prompt(TOBIAS))
    assert request.model == Model.HAIKU_5_5
    [seen] = looked_at(memory, "tobias")
    assert seen.content == (
        f'At the gallery I looked at {KOFI.name}\'s painting "Painting kofi-1". '
        "Loud, but it stays with you."
    )
    assert (seen.work_id, seen.about, seen.topics) == ("kofi-1", ["kofi"], ["squares", "red"])
    assert (seen.valence, seen.salience) == (0.4, 0.6)


def test_a_visitor_looks_at_each_painting_they_have_not_seen_once_then_wanders_between_them(
    works: WorksStore, store: GalleryStore, memory: MemoryStore
) -> None:
    fake = FakeProvider([REACTION] * 3)
    visit = Visit(works, store, memory, LLMClient(fake), [TOBIAS])
    visit.hang(("kofi-1", "kofi"), ("odalys-1", "odalys"), ("tobias-1", "tobias"))
    stood: list[str] = []

    async def wander() -> None:
        for _ in range(60):
            await visit.run(minutes=1)
            if (frame := visit.frame_of("tobias")) and (not stood or stood[-1] != frame):
                stood.append(frame)

    asyncio.run(wander())

    assert sorted(m.work_id for m in looked_at(memory, "tobias")) == ["kofi-1", "odalys-1"]
    assert len(fake.requests) == 2
    assert set(stood) == {frame.id for frame in FRAMES[:3]}
    assert len(stood) > 5


def test_nobody_is_shown_round_unless_they_are_staying_at_the_gallery(
    works: WorksStore, store: GalleryStore, memory: MemoryStore
) -> None:
    visit = Visit(works, store, memory, LLMClient(FakeProvider([])), [TOBIAS, ODALYS])
    visit.hang(("kofi-1", "kofi"))
    visit.minds["tobias"].goal = Goal(Activity.PARK, "park")
    visit.minds["odalys"].paused = True
    before = visit.movement.entities()

    asyncio.run(visit.run(minutes=2))

    assert visit.movement.entities() == before
    assert visit.visitors.walks == {}


def test_a_new_goal_stops_the_walk_round(
    works: WorksStore, store: GalleryStore, memory: MemoryStore
) -> None:
    visit = Visit(works, store, memory, None, [TOBIAS])
    visit.hang(("kofi-1", "kofi"))
    asyncio.run(visit.run(minutes=1.5 / 60))
    assert not visit.visitors.walks["tobias"][0].done

    visit.minds["tobias"].goal = Goal(Activity.TALK, "odalys")
    visit.world.bus.publish(GoalChosen("tobias", "talk", "odalys"))
    stopped = visit.movement.position("tobias")
    asyncio.run(visit.run(minutes=1))

    assert visit.visitors.walks == {}
    assert math.dist(visit.movement.position("tobias"), stopped) <= 1


def test_a_failed_look_is_tried_again_later(
    works: WorksStore, store: GalleryStore, memory: MemoryStore
) -> None:
    fake = FakeProvider([LLMError("usage limit reached"), REACTION])
    visit = Visit(works, store, memory, LLMClient(fake), [TOBIAS])
    visit.hang(("kofi-1", "kofi"))

    asyncio.run(visit.run(minutes=30))
    assert looked_at(memory, "tobias") == []
    asyncio.run(visit.run(minutes=40))

    assert [m.work_id for m in looked_at(memory, "tobias")] == ["kofi-1"]
    assert len(fake.requests) == 2


def test_the_player_remembers_each_painting_they_stand_at_once(
    works: WorksStore, store: GalleryStore, memory: MemoryStore
) -> None:
    visit = Visit(works, store, memory, None, [])
    visit.hang(("kofi-1", "kofi"))
    stand = FRAMES[0].stand[1]

    visit.movement.track(PLAYER_ID, Point(stand.x + 0.3, stand.y - 0.2, "gallery"))
    asyncio.run(visit.run(minutes=1))
    visit.movement.track(PLAYER_ID, Point(16, 15, "gallery"))
    asyncio.run(visit.run(minutes=1))
    visit.movement.track(PLAYER_ID, Point(stand.x, stand.y, "gallery"))
    asyncio.run(visit.run(minutes=1))

    [seen] = looked_at(memory, PLAYER_ID)
    assert seen.content == f'I saw {KOFI.name}\'s painting "Painting kofi-1" at the gallery.'
    assert (seen.work_id, seen.about, seen.valence) == ("kofi-1", ["kofi"], 0)


def test_residents_go_to_the_gallery_and_look_at_the_paintings(
    works: WorksStore, store: GalleryStore, memory: MemoryStore
) -> None:
    world = World(Clock(NOW.replace(hour=10)), FakeWallClock())
    movement = Movement(MAPS, world.bus)
    config = DEFAULT_CONFIG.model_copy(
        update={"base": {Activity.GALLERY: 10.0}, "temperature": 0.0}
    )
    behaviour = Behaviour(world.clock, world.bus, movement, [TOBIAS], config=config, seed=0)
    gallery = Gallery(FRAMES, store, works, world.clock, RESIDENTS)
    for n, artist in enumerate(["kofi", "odalys", "ingrid"]):
        works.add(painting(f"p{n}", artist))
        gallery.hang(painting(f"p{n}", artist), "<svg/>", b"")
    llm = LLMClient(FakeProvider([REACTION] * 3))
    visitors = Visitors(
        gallery, memory, world.clock, lambda: llm, RESIDENTS, behaviour.minds, movement, seed=0
    )
    for system in (behaviour, movement, visitors):
        world.loop.register(system)
    world.bus.subscribe(GoalChosen, visitors.on_goal)
    behaviour.start()

    async def day() -> None:
        for _ in range(round(2 * 3600 / STEP)):
            world.loop.tick()
            await asyncio.sleep(0)
        await asyncio.gather(*visitors.tasks)

    asyncio.run(day())

    assert {m.work_id for m in looked_at(memory, "tobias")} == {"p0", "p1", "p2"}
