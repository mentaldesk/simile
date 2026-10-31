import json
import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import TypeAdapter
from starlette.applications import Starlette

from simile.app import create_app
from simile.persistence import capture, investigation_of, restore
from simile.persistence.lifespan import FRESH_ENV
from simile.schema import Disappearance, Investigation, JournalEntry

from .test_lifespan import run_village, saved
from .test_player import OLD_SAVE, opened, save_from_before_the_player
from .test_state import Village

SCHEMA_TESTS = Path(__file__).parents[1] / "schema"
JOURNAL = TypeAdapter(list[JournalEntry]).validate_json(
    (SCHEMA_TESTS / "journal.json").read_bytes()
)
DISAPPEARANCE = TypeAdapter(list[Disappearance]).validate_json(
    (SCHEMA_TESTS / "disappearances.json").read_bytes()
)[0]
UNDERWAY = Investigation(disappearance=DISAPPEARANCE, journal=JOURNAL)
INCIDENT = {"victim": "aris", "attackers": ["raymond"], "night": "2026-03-06T23:40:00Z"}


def test_a_save_from_before_the_investigation_loads_without_one(tmp_path: Path) -> None:
    path = tmp_path / "simile.db"
    save_from_before_the_player(path)

    with opened(path) as store:
        loaded = store.load()

    assert "investigation" not in json.loads(OLD_SAVE)
    assert loaded is not None and loaded.npcs.keys() == {"desmond", "henrietta"}
    assert loaded.investigation == Investigation()
    assert (loaded.investigation.disappearance, loaded.investigation.journal) == (None, [])


def test_the_investigation_round_trips_through_save_and_load(tmp_path: Path) -> None:
    path = tmp_path / "simile.db"
    with opened(path) as store:
        store.save(capture(Village().behaviour, investigation=UNDERWAY))

    with opened(path) as reopened:
        loaded = reopened.load()

    assert loaded is not None and loaded.investigation == UNDERWAY


def test_capture_saves_an_empty_investigation_without_one() -> None:
    assert capture(Village().behaviour).investigation == Investigation()


def test_capture_takes_a_copy_of_the_investigation() -> None:
    investigation = UNDERWAY.model_copy(deep=True)
    world = capture(Village().behaviour, investigation=investigation)
    assert investigation.disappearance is not None

    investigation.disappearance.distrusted_by.append("priya")
    investigation.journal[2].leads.clear()
    investigation.journal.clear()

    assert world.investigation == UNDERWAY


def test_restore_fills_the_investigation_in_place_with_its_own_copy() -> None:
    village = Village()
    world = capture(village.behaviour, investigation=UNDERWAY)
    investigation = Investigation()

    restore(world, village.behaviour, investigation=investigation)

    assert investigation == UNDERWAY
    assert investigation.journal is not world.investigation.journal
    assert investigation.journal[0] is not world.investigation.journal[0]


async def investigate(app: Starlette) -> None:
    investigation = investigation_of(app)
    investigation.disappearance = DISAPPEARANCE.model_copy(deep=True)
    investigation.journal = [entry.model_copy(deep=True) for entry in JOURNAL]


@pytest.mark.anyio
async def test_the_investigation_survives_a_restart(database: Path) -> None:
    await run_village(timedelta(minutes=5), after=investigate)
    assert saved(database).investigation == UNDERWAY

    async def resumed(app: Starlette) -> None:
        assert investigation_of(app) == UNDERWAY

    await run_village(timedelta(minutes=5), before=resumed)
    assert saved(database).investigation == UNDERWAY


@pytest.mark.anyio
async def test_an_investigation_taken_before_startup_is_the_one_restored_and_saved(
    database: Path,
) -> None:
    await run_village(timedelta(minutes=1), after=investigate)
    app = create_app()
    early = investigation_of(app)

    async def follow_a_lead(app: Starlette) -> None:
        assert investigation_of(app) is early
        assert early == UNDERWAY
        early.journal[2].leads = []

    await run_village(timedelta(minutes=1), app=app, after=follow_a_lead)
    assert saved(database).investigation.journal[2].leads == []


@pytest.mark.anyio
async def test_a_save_from_before_the_investigation_starts_with_an_empty_journal(
    database: Path,
) -> None:
    save_from_before_the_player(database)

    async def empty(app: Starlette) -> None:
        assert investigation_of(app).journal == []

    await run_village(timedelta(minutes=1), before=empty)
    assert saved(database).investigation.journal == []


@pytest.mark.anyio
async def test_a_fresh_start_forgets_the_investigation(
    database: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    await run_village(timedelta(minutes=1), after=investigate)
    assert saved(database).investigation == UNDERWAY
    monkeypatch.setenv(FRESH_ENV, "1")

    async def forgotten(app: Starlette) -> None:
        investigation = investigation_of(app)
        assert investigation.journal == [] and investigation.disappearance != DISAPPEARANCE

    await run_village(timedelta(minutes=1), before=forgotten)
    assert saved(database).investigation.journal == []
    assert saved(database).investigation.disappearance != DISAPPEARANCE


@pytest.mark.anyio
async def test_a_save_with_an_incident_starts_with_a_disappearance_keeping_what_s_true(
    database: Path,
) -> None:
    await run_village(timedelta(minutes=1))
    journal = [entry.model_dump(mode="json") for entry in JOURNAL]
    with sqlite3.connect(database) as db:
        [(data,)] = db.execute("SELECT data FROM saved_world").fetchall()
        old = json.loads(data) | {"investigation": {"incident": INCIDENT, "journal": journal}}
        db.execute("UPDATE saved_world SET data = ?", (json.dumps(old),))

    await run_village(timedelta(minutes=1))

    investigation = saved(database).investigation
    assert investigation.disappearance is not None
    true = {fact.id: fact.what for fact in investigation.disappearance.facts}
    kept = [(entry.fact_id, entry.text) for entry in investigation.journal]
    assert kept and kept == [(e.fact_id, e.text) for e in JOURNAL if true.get(e.fact_id) == e.text]
    with sqlite3.connect(database) as db:
        [(data,)] = db.execute("SELECT data FROM saved_world").fetchall()
    assert "incident" not in json.loads(data)["investigation"]


@pytest.mark.anyio
async def test_with_an_in_memory_database_the_investigation_starts_afresh_and_unsaved() -> None:
    async def check(app: Starlette) -> None:
        assert not hasattr(app.state, "persistence")
        assert investigation_of(app) is investigation_of(app)
        assert investigation_of(app).journal == []

    await run_village(timedelta(minutes=1), before=check)
