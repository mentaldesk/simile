import json
import sqlite3
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from starlette.applications import Starlette

from simile.app import create_app
from simile.behaviour.mind import create_behaviour
from simile.conversation import conversations_of, create_engine
from simile.memory import MemoryStore, memory_of
from simile.persistence import WorldStore, investigation_of
from simile.persistence.lifespan import FRESH_ENV
from simile.schema import Incident, Memory
from simile.sim import Clock, FakeWallClock, World, world_of
from simile.story.begin import begin
from simile.story.incident import ATTACK

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
    """Persistence's saver, noting what the store held when it saved."""

    def __init__(self, memory: MemoryStore) -> None:
        self.memory = memory
        self.held: list[int] = []

    async def save(self) -> None:
        self.held.append(sum(len(self.memory.facts(npc)) for npc in ("raymond", "henrietta")))


async def test_the_incident_is_saved_before_its_memories_are_stored() -> None:
    app = Starlette()
    app.state.world = World(Clock(START), FakeWallClock())
    app.state.memory = memory = MemoryStore(":memory:")
    app.state.behaviour = create_behaviour(app, seed=0)
    app.state.persistence = saver = Saver(memory)

    incident = await begin(app)

    assert incident is not None and investigation_of(app).incident is incident
    assert saver.held == [0]
    assert memory.facts(incident.attackers[0])
    assert await begin(app) is None and saver.held == [0]
