import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from simile.casting import load_cast
from simile.cli import create_cli
from simile.memory import MemoryStore
from simile.memory.store import DEFAULT_PATH
from simile.npc import NPCS_DIR, load_npcs
from simile.persistence import SavedWorld, WorldStore
from simile.schema import Character, HookKind

runner = CliRunner()
CONTENT = NPCS_DIR.parent
COLOUR = re.compile(r"\x1b\[[0-9;]*m")


def said(result: Result) -> str:
    """The CLI's output without colours, the error box's borders or line wrapping."""
    return " ".join(COLOUR.sub("", result.output).replace("│", " ").split())


def snapshot() -> dict[Path, bytes]:
    folders = [CONTENT / "npcs", CONTENT / "voices", CONTENT / "characters" / "pool"]
    return {path: path.read_bytes() for f in folders for path in f.rglob("*") if path.is_file()}


def test_cast_random_makes_a_new_world_and_leaves_content_alone(world: Path) -> None:
    before = snapshot()

    result = runner.invoke(create_cli(), ["cast", "--random", "10", "--seed", "5"])

    assert result.exit_code == 0, result.output
    made = load_cast()
    assert made is not None and len(made.residents) == 10
    assert {npc.id for npc in load_npcs()} == {r.character.id for r in made.residents}
    assert f"SIMILE_DB={world / 'simile.db'} uv run simile headless" in result.output
    if unvoiced := made.unvoiced():
        assert f"No voice clip yet for {len(unvoiced)} of them" in result.output
    assert not (world / "simile.db").exists()
    assert snapshot() == before


def test_cast_pick_and_pin(tmp_path: Path, pool: list[Character]) -> None:
    a, b, c = (character.id for character in pool[:3])

    result = runner.invoke(
        create_cli(),
        ["cast", "--pick", f"{a},{b}", "--pin", f"{c}:old_friend:{a}", "--data", str(tmp_path)],
    )

    assert result.exit_code == 0, result.output
    made = load_cast(tmp_path)
    assert made is not None
    assert [r.character.id for r in made.residents] == [a, b, c]
    assert (made.bonds[0].kind, made.bonds[0].actor, made.bonds[0].pinned) == (
        HookKind.OLD_FRIEND,
        c,
        True,
    )


@pytest.mark.parametrize(
    ("args", "error"),
    [
        (["--random", "11"], "10 houses, too few for 11"),
        (["--pin", "a:cousin:b"], "'a:cousin:b'"),
        (["--pin", "a-b"], "isn't actor:kind:target"),
        ([], "pass --random N"),
    ],
)
def test_cast_refuses_what_it_cant_make(tmp_path: Path, args: list[str], error: str) -> None:
    result = runner.invoke(create_cli(), ["cast", *args, "--data", str(tmp_path)])

    assert result.exit_code == 2
    assert error in said(result)
    assert not (tmp_path / "cast").exists()


def test_cast_refuses_a_date_before_a_residents_birth(tmp_path: Path) -> None:
    result = runner.invoke(
        create_cli(), ["cast", "--random", "3", "--date", "1900-01-01", "--data", str(tmp_path)]
    )

    assert result.exit_code == 2
    assert "1900-01-01 is too early for" in said(result)
    assert not (tmp_path / "cast").exists()


def test_cast_refuses_where_simile_db_holds_todays_village(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    save = tmp_path / "today" / "village.sqlite"
    monkeypatch.setenv("SIMILE_DB", str(save))
    with MemoryStore(save) as memory, WorldStore(memory) as store:
        store.save(SavedWorld(now=datetime(2026, 1, 1, 8, tzinfo=UTC), npcs={}))

    result = runner.invoke(create_cli(), ["cast", "--random", "10"])

    assert result.exit_code == 2
    assert "already holds a saved village in village.sqlite" in said(result)
    assert sorted(path.name for path in save.parent.iterdir()) == ["village.sqlite"]
    assert {npc.id for npc in load_npcs()} == {npc.id for npc in load_npcs(NPCS_DIR)}


def test_cast_needs_a_data_directory_of_its_own(monkeypatch: pytest.MonkeyPatch) -> None:
    before = (DEFAULT_PATH.parent / "cast").exists()

    in_memory = runner.invoke(create_cli(), ["cast", "--random", "3"])
    monkeypatch.delenv("SIMILE_DB")
    default = runner.invoke(create_cli(), ["cast", "--random", "3"])

    assert in_memory.exit_code == 2
    assert "data directory" in said(in_memory)
    assert default.exit_code == 2
    assert "holds today's village" in said(default)
    assert (DEFAULT_PATH.parent / "cast").exists() == before
