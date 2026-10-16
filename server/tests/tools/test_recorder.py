import logging
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette

from simile.app import create_app
from simile.behaviour.mind import create_behaviour
from simile.conversation import create_engine
from simile.memory import memory_of
from simile.schema import Relationship
from simile.sim import Clock, FakeWallClock, World
from simile.social import meet
from simile.tools import RecordStore, load_run, report
from simile.tools.lifespan import RECORD_ENV

START = datetime(2026, 1, 1, 9, tzinfo=UTC)


@pytest.fixture
def database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "data" / "simile.db"
    monkeypatch.setenv("SIMILE_DB", str(path))
    return path


@pytest.fixture
def recording(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(RECORD_ENV, "1")


async def run_village(duration: timedelta) -> Starlette:
    app = create_app()
    world = World(Clock(START), FakeWallClock())
    app.state.world = world
    app.state.headless = True
    app.state.behaviour = create_behaviour(app, seed=0)
    app.state.conversation = create_engine(app, seed=0)
    async with app.router.lifespan_context(app):
        await world.loop.run(duration)
    return app


@pytest.mark.anyio
@pytest.mark.usefixtures("recording")
async def test_records_where_everyone_is_what_they_said_and_the_llm_calls(database: Path) -> None:
    app = await run_village(timedelta(hours=1))

    run = load_run(database)
    npcs = sorted(app.state.behaviour.npcs)
    assert (run.id, run.npcs, run.speed) == (1, npcs, 1.0)
    assert (run.started, run.ended) == (START, START + timedelta(hours=1))
    assert run.real_seconds is not None
    assert len(run.samples) == 60 * len(npcs)
    assert {s.npc for s in run.samples} == set(npcs)
    assert {s.time for s in run.samples} == {
        START + timedelta(minutes=m, seconds=0.1 if m == 0 else 0) for m in range(60)
    }
    assert run.conversations
    assert all(c.ended and c.lines for c in run.conversations)
    lines = sum(len(c.lines) for c in run.conversations)
    assert sum(call.purpose == "conversation" for call in run.calls) >= lines
    assert {call.provider for call in run.calls} == {"canned"}
    assert any(call.purpose == "reflection" for call in run.calls)
    summary = report(run)
    assert "> **Fake provider.**" in summary
    assert "- B3 stored no memories, events or flags from" in summary
    assert f"| {npcs[0]} |" in summary


@pytest.mark.anyio
@pytest.mark.usefixtures("recording")
async def test_takes_every_relationship_at_the_start_and_the_end(database: Path) -> None:
    app = create_app()
    world = World(Clock(START), FakeWallClock())
    app.state.world = world
    app.state.headless = True
    app.state.behaviour = behaviour = create_behaviour(app, seed=0)
    kofi = behaviour.npcs["kofi"]
    known = meet(kofi, "tobias").model_copy(update={"like": 0.9, "familiarity": 0.5})
    memory_of(app).add(known)
    async with app.router.lifespan_context(app):
        memory_of(app).add(Relationship.model_validate(known.model_dump() | {"like": 0.2}))
        await world.loop.run(timedelta(minutes=5))

    run = load_run(database)
    pairs = len(behaviour.npcs) * (len(behaviour.npcs) - 1)
    assert len(run.start) == len(run.end) == pairs
    assert run.start["kofi", "tobias"].like == 0.9
    assert run.end["kofi", "tobias"].like == 0.2
    assert run.start["tobias", "kofi"] == meet(behaviour.npcs["tobias"], "kofi")


@pytest.mark.anyio
@pytest.mark.usefixtures("recording")
async def test_each_run_is_recorded_separately(database: Path) -> None:
    await run_village(timedelta(minutes=10))
    await run_village(timedelta(minutes=20))

    assert load_run(database, 1).ended - load_run(database, 1).started == timedelta(minutes=10)
    latest = load_run(database)
    assert latest.id == 2
    assert latest.started == START + timedelta(minutes=10)
    assert len(latest.samples) == 20 * len(latest.npcs)


@pytest.mark.anyio
@pytest.mark.usefixtures("recording")
async def test_a_failed_write_is_logged_and_retried_without_stopping_the_sim(
    database: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    add = RecordStore.add
    failures = iter([True, True])

    def locked(store: RecordStore, run: int, **rows: Any) -> None:
        if rows.get("samples") and next(failures, False):
            raise sqlite3.OperationalError("database is locked")
        add(store, run, **rows)

    monkeypatch.setattr(RecordStore, "add", locked)
    with caplog.at_level(logging.ERROR, logger="simile.tools.recorder"):
        await run_village(timedelta(minutes=5))

    assert caplog.text.count("Couldn't record run 1") == 2
    assert len(load_run(database).samples) == 5 * len(load_run(database).npcs)


@pytest.mark.anyio
async def test_records_nothing_unless_asked(database: Path) -> None:
    await run_village(timedelta(minutes=5))

    with sqlite3.connect(database) as db:
        tables = {name for (name,) in db.execute("SELECT name FROM sqlite_master")}
    assert not any(name.startswith("record_") for name in tables)


@pytest.mark.anyio
@pytest.mark.usefixtures("recording")
async def test_an_in_memory_database_records_nothing(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="simile.tools.lifespan"):
        app = await run_village(timedelta(minutes=5))

    assert not hasattr(app.state, "recorder")
    assert "nothing is recorded" in caplog.text
