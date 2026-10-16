from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from simile.cli import create_cli
from simile.memory import MemoryStore
from simile.persistence import SavedWorld, WorldStore
from simile.schema import Relationship

runner = CliRunner()


def save_a_village(database: Path, relationships: list[Relationship]) -> SavedWorld:
    world = SavedWorld(now=datetime(2026, 1, 1, 8, tzinfo=UTC), npcs={})
    with MemoryStore(database) as memory, WorldStore(database) as store:
        memory.add(*relationships)
        store.save(world)
    return world


def test_reset_forgets_the_saved_village(database: Path, relationships: list[Relationship]) -> None:
    save_a_village(database, relationships)

    result = runner.invoke(create_cli(), ["reset", "--yes"])

    assert result.exit_code == 0, result.output
    with MemoryStore(database) as memory, WorldStore(database) as store:
        assert memory.relationships("mei") == []
        assert store.load() is None


def test_reset_asks_first(database: Path, relationships: list[Relationship]) -> None:
    world = save_a_village(database, relationships)

    result = runner.invoke(create_cli(), ["reset"], input="n\n")

    assert result.exit_code == 1
    assert str(database) in result.output
    with MemoryStore(database) as memory, WorldStore(database) as store:
        assert memory.relationships("mei") != []
        assert store.load() == world


def test_reset_with_nothing_saved(database: Path) -> None:
    result = runner.invoke(create_cli(), ["reset"])

    assert result.exit_code == 0, result.output
    assert "Nothing saved" in result.output
    assert not database.exists()
