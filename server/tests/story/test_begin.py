import json
import random
import sqlite3
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.applications import Starlette

from simile.app import create_app
from simile.behaviour import behaviour_of
from simile.behaviour.mind import create_behaviour
from simile.casting.history import seeded
from simile.conversation import conversations_of, create_engine
from simile.memory import MemoryStore, memory_of
from simile.persistence import WorldStore, investigation_of
from simile.persistence.lifespan import FRESH_ENV
from simile.schema import Incident, Memory, Npc
from simile.sim import Clock, FakeWallClock, World, world_of
from simile.story import begin as story_begin
from simile.story.begin import begin
from simile.story.content import TERMINAL
from simile.story.incident import ATTACK, GONE, LIFT_LOG, lift_log, make_incident
from simile.story.journal import Journal

pytestmark = pytest.mark.anyio

START = datetime(2026, 1, 1, 8, tzinfo=UTC)

type Step = Callable[[Starlette], Awaitable[None]]


async def nothing(app: Starlette) -> None:
    pass


async def run_village(during: Step = nothing, minutes: float = 1) -> Starlette:
    """Start every module on `SIMILE_DB`, do `during`, run for a minute and shut down."""
    app = create_app()
    world = World(Clock(START), FakeWallClock())
    app.state.world = world
    app.state.headless = True
    app.state.behaviour = create_behaviour(app, seed=0)
    app.state.conversation = create_engine(app, seed=0)
    async with app.router.lifespan_context(app):
        await during(app)
        await world.loop.run(timedelta(minutes=minutes))
    return app


@pytest.fixture
def database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "data" / "simile.db"
    monkeypatch.setenv("SIMILE_DB", str(path))
    return path


def saved(database: Path) -> Incident | None:
    with MemoryStore(database) as memory, WorldStore(memory) as store:
        world = store.load()
    assert world is not None
    return world.investigation.incident


def remembered(database: Path) -> list[Memory]:
    with MemoryStore(database) as memory:
        return [m for npc in ("desmond", "henrietta", "raymond") for m in memory.facts(npc)]


async def test_a_new_world_makes_its_incident_and_its_residents_remember_it() -> None:
    async def check(app: Starlette) -> None:
        incident = investigation_of(app).incident
        assert incident is not None
        assert conversations_of(app).incident() is incident
        memory, now = memory_of(app), world_of(app).clock.now
        for npc in incident.attackers:
            assert ATTACK in {m.fact_id for m in memory.facts(npc)}
            assert all(m.fact_id is None for m in memory.recall(npc, now, k=100))

    await run_village(check)


async def test_the_incident_is_made_once_and_kept_across_restarts(database: Path) -> None:
    await run_village()
    first, memories = saved(database), remembered(database)
    assert first is not None and memories

    await run_village()

    assert saved(database) == first
    assert remembered(database) == memories


async def test_a_save_from_before_the_incident_gets_one_on_its_next_start(
    database: Path,
) -> None:
    await run_village()
    with sqlite3.connect(database) as db:
        [(data,)] = db.execute("SELECT data FROM saved_world").fetchall()
        old = {key: value for key, value in json.loads(data).items() if key != "investigation"}
        db.execute("UPDATE saved_world SET data = ?", (json.dumps(old),))
        db.execute("DELETE FROM memories WHERE json_extract(data, '$.fact_id') IS NOT NULL")
    assert saved(database) is None and remembered(database) == []

    await run_village()
    made, memories = saved(database), remembered(database)
    await run_village()

    assert made is not None and memories
    assert saved(database) == made and remembered(database) == memories


async def test_a_fresh_start_makes_a_new_incident_in_place_of_the_old(
    database: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    await run_village()
    monkeypatch.setenv(FRESH_ENV, "1")

    await run_village()

    incident = saved(database)
    assert incident is not None
    knowers = [
        (k.id, fact.id)
        for fact in incident.facts
        for k in fact.known_by
        if k.id in ("desmond", "henrietta", "raymond")
    ]
    assert sorted((m.owner, m.fact_id) for m in remembered(database)) == sorted(knowers)


class Saver:
    """Persistence's saver, noting the incident and how many of its memories were stored."""

    def __init__(self, app: Starlette) -> None:
        self.app = app
        self.held: list[tuple[Incident | None, int]] = []

    async def save(self) -> None:
        stored = sum(len(memory_of(self.app).facts(npc)) for npc in behaviour_of(self.app).npcs)
        self.held.append((investigation_of(self.app).incident, stored))


def starting(npcs: list[Npc] | None = None) -> Starlette:
    """An app with a world, a store, residents and a saver, before the story begins."""
    app = Starlette()
    app.state.world = World(Clock(START), FakeWallClock())
    app.state.memory = MemoryStore(":memory:")
    app.state.behaviour = create_behaviour(app, seed=0, npcs=npcs)
    app.state.persistence = Saver(app)
    return app


async def test_the_memories_are_stored_before_the_incident_is_saved() -> None:
    app = starting()

    incident = await begin(app)

    assert incident is not None and investigation_of(app).incident is incident
    knowers = sum(len(fact.known_by) for fact in incident.facts)
    assert app.state.persistence.held == [(incident, knowers)]
    assert await begin(app) is None and len(app.state.persistence.held) == 1


async def test_memories_left_from_an_incident_never_saved_are_forgotten_first() -> None:
    app = starting()
    memory = memory_of(app)
    left = await make_incident(list(behaviour_of(app).npcs.values()), START, None)
    memory.add(*left.memories, *(m.model_copy(update={"fact_id": None}) for m in left.memories[:2]))

    incident = await begin(app, rng=random.Random(1))

    assert incident is not None
    stored = [m for npc in behaviour_of(app).npcs for m in memory.facts(npc)]
    assert len(stored) == sum(len(fact.known_by) for fact in incident.facts)
    everyday = [m for npc in behaviour_of(app).npcs for m in memory.recall(npc, START, k=100)]
    assert len(everyday) == 2


async def test_a_world_with_no_residents_has_no_incident() -> None:
    app = starting(npcs=[])

    assert await begin(app) is None
    assert investigation_of(app).incident is None
    assert app.state.persistence.held == []


async def test_a_cast_world_draws_its_incident_from_the_casts_seed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(story_begin, "load_cast", lambda: SimpleNamespace(seed=42))
    first, second = starting(), starting()

    assert await begin(first) == await begin(second)


async def test_casting_never_takes_the_incidents_memories_for_a_village_that_ran() -> None:
    app = starting()

    incident = await begin(app)

    assert incident is not None
    residents = list(behaviour_of(app).npcs)
    assert not seeded(memory_of(app), residents, START)


async def test_an_incident_from_before_s8_gains_the_lift_log_once_and_the_terminal_finds_it() -> (
    None
):
    app = starting()
    made = await begin(app)
    assert made is not None
    investigation = investigation_of(app)
    investigation.incident = made.model_copy(
        update={"facts": [fact for fact in made.facts if fact.id != LIFT_LOG]}
    )
    saves = len(app.state.persistence.held)

    assert await begin(app) is None and await begin(app) is None

    facts = {fact.id: fact for fact in investigation.incident.facts}
    assert facts[LIFT_LOG] == lift_log(facts[GONE].when)
    assert facts[LIFT_LOG].when == facts[GONE].when - timedelta(hours=20)
    assert [fact.id for fact in investigation.incident.facts].count(LIFT_LOG) == 1
    assert len(app.state.persistence.held) == saves + 1
    assert Journal(investigation, lambda: START).found(TERMINAL, "Dead terminal")
    assert [entry.fact_id for entry in investigation.journal] == [LIFT_LOG]
