import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from simile.casting import (
    Cast,
    CastRefused,
    bind,
    cast,
    cast_npcs,
    check_writable,
    holds_save,
    load_cast,
    write_cast,
)
from simile.memory import MemoryStore
from simile.memory.store import DEFAULT_PATH
from simile.npc import NPCS_DIR, load_npcs
from simile.persistence import SavedWorld, WorldStore
from simile.schema import Character, Memory, MemoryKind

HOUSES = [f"house_{n}" for n in range(1, 11)]


@pytest.fixture
def made(pool: list[Character]) -> Cast:
    return bind(cast(pool, 4, seed=2, houses=10), seed=2, houses=HOUSES)


def test_without_a_cast_load_npcs_reads_content(world: Path) -> None:
    today = load_npcs(NPCS_DIR)

    assert load_npcs() == today
    assert cast_npcs() is None


def test_in_memory_load_npcs_reads_content(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIMILE_DB", ":memory:")

    assert load_npcs() == load_npcs(NPCS_DIR)


def test_load_npcs_reads_the_cast_in_the_data_directory(world: Path, made: Cast) -> None:
    write_cast(made, world)

    assert load_npcs() == sorted(made.npcs(), key=lambda npc: npc.id)
    assert load_cast() == made
    assert load_cast(world) == made


def test_a_cast_that_never_ran_is_replaced(world: Path, made: Cast, pool: list[Character]) -> None:
    write_cast(made, world)
    other = bind(cast(pool, 3, seed=8, houses=10), seed=8, houses=HOUSES)

    write_cast(other, world)

    assert {npc.id for npc in load_npcs()} == {npc.id for npc in other.npcs()}


@pytest.mark.parametrize(
    "where",
    [
        DEFAULT_PATH.parent,
        Path(str(DEFAULT_PATH.parent).upper()),
        DEFAULT_PATH.parent / ".." / "data",
        DEFAULT_PATH.parent / "worlds" / "new",
        NPCS_DIR.parent,
        NPCS_DIR.parent / "characters" / "worlds",
    ],
)
def test_todays_village_and_content_are_refused(made: Cast, where: Path) -> None:
    before = (DEFAULT_PATH.parent / "cast").exists()

    with pytest.raises(CastRefused):
        write_cast(made, where)

    assert (DEFAULT_PATH.parent / "cast").exists() == before
    assert not (NPCS_DIR.parent / "cast").exists()


def test_a_data_directory_with_a_saved_village_is_refused(tmp_path: Path) -> None:
    with MemoryStore(tmp_path / "simile.db") as memory, WorldStore(memory) as store:
        store.save(SavedWorld(now=datetime(2026, 1, 1, 8, tzinfo=UTC), npcs={}))

    with pytest.raises(CastRefused, match="already holds a saved village in simile.db"):
        check_writable(tmp_path)


@pytest.mark.parametrize("name", ["village.sqlite", "save", "simile.db.bak"])
def test_a_save_is_found_whatever_its_name(tmp_path: Path, name: str) -> None:
    with MemoryStore(tmp_path / name) as memory, WorldStore(memory) as store:
        store.save(SavedWorld(now=datetime(2026, 1, 1, 8, tzinfo=UTC), npcs={}))
    (tmp_path / "notes.txt").write_text("not a database")

    with pytest.raises(CastRefused, match=rf"saved village in {re.escape(name)}\. "):
        check_writable(tmp_path)


def test_the_save_simile_db_points_at_is_checked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SIMILE_DB", str(tmp_path / "village"))
    (tmp_path / "village").write_text("not a database")
    (tmp_path / "unrelated").write_text("not a database either")

    with pytest.raises(CastRefused, match=r"saved village in village\. "):
        check_writable(tmp_path)


def test_r2_records_alone_count_as_a_save(tmp_path: Path) -> None:
    memory = Memory(
        owner="kofi",
        kind=MemoryKind.OBSERVATION,
        content="Saw a mural.",
        salience=0.5,
        valence=0.2,
        timestamp=datetime(2026, 1, 1, 8, tzinfo=UTC),
    )
    with MemoryStore(tmp_path / "other.db") as store:
        assert not holds_save(tmp_path / "other.db")
        store.add(memory)

    assert holds_save(tmp_path / "other.db")


def test_news_alone_and_a_missing_database_are_not_a_save(tmp_path: Path) -> None:
    with sqlite3.connect(tmp_path / "simile.db") as db:
        db.execute("CREATE TABLE news (id TEXT)")
        db.execute("INSERT INTO news VALUES ('a')")

    check_writable(tmp_path)
    check_writable(tmp_path / "new")


def test_a_file_that_isnt_a_database_counts_as_a_save(tmp_path: Path) -> None:
    (tmp_path / "simile.db").write_text("not a database")

    assert holds_save(tmp_path / "simile.db")


def test_a_cast_folder_that_isnt_a_cast_is_refused(tmp_path: Path, made: Cast) -> None:
    (tmp_path / "cast").mkdir()
    (tmp_path / "cast" / "notes.txt").write_text("mine")

    with pytest.raises(CastRefused, match="isn't a cast"):
        write_cast(made, tmp_path)

    assert (tmp_path / "cast" / "notes.txt").read_text() == "mine"
