import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from starlette.testclient import TestClient

from simile.app import create_app
from simile.behaviour import DEFAULT_CONFIG, Activity, Behaviour, Goal, Need, behaviour_of
from simile.behaviour.inspiration import inspiration, touches
from simile.behaviour.simulate import report, simulate
from simile.memory import memory_of
from simile.npc import NPCS_DIR, load_npcs
from simile.schema import (
    PLAYER_ID,
    CoreValue,
    Craft,
    Medium,
    Memory,
    MemoryKind,
    Npc,
    Shift,
    Weekday,
)
from simile.sim import STEP, Clock, FakeWallClock, World
from simile.world import Movement
from simile.world.map import load_maps

MAPS = load_maps()
MORNING = datetime(2026, 1, 1, 8, tzinfo=UTC)
RESIDENTS = {npc.id: npc for npc in load_npcs(NPCS_DIR)}
KOFI = RESIDENTS["kofi"]
NO_WORK = {"workplace": None, "shifts": [], "pay": None}
CAP = DEFAULT_CONFIG.inspiration_cap


def resident(id: str, home: str, medium: Medium | None = Medium.WRITING, **values: float) -> Npc:
    craft = Craft(medium=medium, form="short poems about the sea") if medium else None
    return RESIDENTS["desmond"].model_copy(
        update={
            "id": id,
            "name": id.title(),
            "home": home,
            "values": {value: values.get(value.value, 0.5) for value in CoreValue},
            "craft": craft,
            **NO_WORK,
        }
    )


WREN = resident("wren", "house_1", justice=0.9, compassion=0.85, honesty=0.8)


def memory(
    owner: str = "wren",
    *,
    salience: float = 0.5,
    valence: float = 0.4,
    topics: tuple[str, ...] = ("the weather",),
    kind: MemoryKind = MemoryKind.CONVERSATION,
    about: tuple[str, ...] = ("ben",),
    at: datetime = MORNING,
) -> Memory:
    return Memory(
        owner=owner,
        kind=kind,
        content="Something happened.",
        salience=salience,
        valence=valence,
        timestamp=at,
        about=list(about),
        topics=list(topics),
    )


class Village:
    def __init__(self, npcs: list[Npc], *, start: datetime = MORNING, **config: object) -> None:
        self.world = World(Clock(start), FakeWallClock())
        self.movement = Movement(MAPS, self.world.bus)
        self.behaviour = Behaviour(
            self.world.clock,
            self.world.bus,
            self.movement,
            npcs,
            config=DEFAULT_CONFIG.model_copy(update=config),
            seed=0,
        )
        self.world.loop.register(self.behaviour)
        self.world.loop.register(self.movement)
        self.behaviour.start()

    def run(self, minutes: float) -> None:
        for _ in range(round(minutes * 60 / STEP)):
            self.world.loop.tick()


def test_a_stronger_memory_inspires_more() -> None:
    weak = inspiration(memory(salience=0.2, valence=0.1), WREN)
    felt = inspiration(memory(salience=0.2, valence=-0.9), WREN)
    strong = inspiration(memory(salience=0.9, valence=0.8), WREN)

    assert 0 < weak < felt < strong < CAP


def test_one_touching_their_craft_inspires_more_than_one_that_doesnt() -> None:
    plain = inspiration(memory(topics=("the weather",)), WREN)

    assert inspiration(memory(topics=("poetry night",)), WREN) > plain
    assert inspiration(memory(topics=("the sea wall",)), WREN) == plain
    assert inspiration(memory(topics=("short stories",)), WREN) > plain


def test_one_touching_their_strongest_values_inspires_more_than_one_that_doesnt() -> None:
    plain = inspiration(memory(topics=("the weather",)), WREN)

    assert inspiration(memory(topics=("unfair rent rises",)), WREN) > plain
    assert inspiration(memory(topics=("old traditions",)), WREN) == plain


def test_each_memory_adds_at_most_the_cap() -> None:
    stirring = memory(salience=1.0, valence=1.0, topics=("poetry", "justice"))

    assert inspiration(stirring, WREN) == CAP


def test_conversations_articles_and_others_works_inspire_and_nothing_else_does() -> None:
    def adds(**fields: object) -> float:
        return inspiration(memory(**fields), WREN)  # type: ignore[arg-type]

    assert adds(kind=MemoryKind.CONVERSATION, about=(PLAYER_ID,)) > 0
    assert adds(kind=MemoryKind.NEWS, about=()) > 0
    assert adds(kind=MemoryKind.WORK, about=("kofi",)) > 0
    assert adds(kind=MemoryKind.WORK, about=()) == 0
    assert adds(kind=MemoryKind.PAST) == 0
    assert adds(kind=MemoryKind.OBSERVATION) == 0
    assert adds(owner="ben") == 0
    assert inspiration(memory(owner="ben"), resident("ben", "house_2", medium=None)) == 0


def test_topics_match_whole_words_their_beginnings_and_phrases() -> None:
    assert touches(["Street Art festival"], ["street art"])
    assert touches(["murals"], ["mural"])
    assert not touches(["the artichoke stall"], ["art"])
    assert not touches(["a startling idea"], ["art"])


def test_new_memories_raise_a_crafters_inspiration_up_to_a_cap_each_sim_hour() -> None:
    village = Village([WREN], head_starts=0)
    mind = village.behaviour.minds["wren"]
    mind.needs[Need.INSPIRATION] = 0.1
    stirring = memory(salience=1.0, valence=1.0, topics=("poetry",))

    added = [village.behaviour.inspire(stirring) for _ in range(3)]

    assert added == pytest.approx([CAP, DEFAULT_CONFIG.inspiration_hourly - CAP, 0.0])
    assert mind.needs[Need.INSPIRATION] == pytest.approx(0.1 + DEFAULT_CONFIG.inspiration_hourly)
    village.run(minutes=61)
    assert village.behaviour.inspire(stirring) == pytest.approx(CAP)


def test_talking_through_a_mural_idea_takes_kofi_close_to_painting() -> None:
    village = Village([KOFI.model_copy(update=NO_WORK)], head_starts=0)
    mind = village.behaviour.minds["kofi"]
    mind.needs[Need.INSPIRATION] = 0.30
    idea = memory(
        "kofi",
        salience=0.8,
        valence=0.7,
        topics=("mural idea", "coffee"),
        about=(PLAYER_ID,),
    )

    village.behaviour.inspire(idea)

    assert mind.needs[Need.INSPIRATION] > 0.55
    assert inspiration(idea.model_copy(update={"topics": ["the weather"]}), KOFI) < 0.15


def makers(village: Village) -> dict[str, Goal]:
    return {
        npc: mind.goal
        for npc, mind in village.behaviour.minds.items()
        if mind.goal.activity is Activity.CREATE
    }


def test_on_a_fresh_start_the_keenest_two_are_already_making_something_at_home() -> None:
    writers = [resident(f"w{n}", f"house_{n}") for n in range(1, 5)]
    muralist = resident("mo", "house_5", medium=Medium.MURAL)
    village = Village([*writers, muralist, resident("nan", "house_6", medium=None)])
    made: list[str] = []
    village.behaviour.hooks.set(create=lambda npc, wall, intention: made.append(npc.id))
    minds = village.behaviour.minds
    keenest = sorted((w.id for w in writers), key=lambda id: -minds[id].needs[Need.INSPIRATION])[:2]

    assert makers(village) == {id: Goal(Activity.CREATE, minds[id].npc.home) for id in keenest}
    for id in keenest:
        left = minds[id].until - MORNING  # type: ignore[operator]
        assert timedelta(minutes=4) <= left <= timedelta(minutes=12)
    village.run(minutes=12.5)
    assert sorted(made) == sorted(keenest)


def test_nobody_asleep_or_off_to_work_gets_a_head_start() -> None:
    asleep = Village([resident("w1", "house_1")], start=MORNING.replace(hour=3))
    assert makers(asleep) == {}

    due = resident("w1", "house_1").model_copy(
        update={
            "workplace": "maker_space",
            "shifts": [Shift(days=list(Weekday), start=8.0, end=12.0)],
        }
    )
    assert makers(Village([due])) == {}
    assert makers(Village([resident("w1", "house_1")], head_starts=0)) == {}


def test_the_server_raises_inspiration_from_new_memories_until_it_stops(
    make_package: Callable[[dict[str, str]], str],
) -> None:
    package = make_package(
        {
            f"{module}/lifespan.py": f"from simile.{module}.lifespan import lifespan\n"
            for module in ("behaviour", "memory")
        }
    )
    app = create_app(package)

    with TestClient(app):
        behaviour, store = behaviour_of(app), memory_of(app)
        before = behaviour.needs("kofi")[Need.INSPIRATION]
        store.add(memory("kofi", at=behaviour.clock.now))
        assert behaviour.needs("kofi")[Need.INSPIRATION] > before

    assert store._listeners == []


def test_the_simulator_starts_with_a_work_soon_and_reports_the_pace() -> None:
    observer, seconds = asyncio.run(simulate(1, start=MORNING, talk=5))
    summary = report(observer, 1, MORNING, 0, seconds)

    assert observer.made and observer.made[0][0] - MORNING <= timedelta(minutes=15)
    assert f"{len(observer.made)} works. The first after " in summary
