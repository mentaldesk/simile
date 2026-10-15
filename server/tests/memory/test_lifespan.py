import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from simile.app import create_app
from simile.memory import MemoryStore, memory_of
from simile.schema import Memory, MemoryKind

MakePackage = Callable[[dict[str, str]], str]

NOW = datetime(2026, 3, 14, 12, tzinfo=UTC)
REMEMBERED = Memory(
    owner="mei", kind=MemoryKind.OBSERVATION, content="hi", salience=1, valence=0, timestamp=NOW
)


@pytest.fixture
def package(make_package: MakePackage) -> str:
    return make_package({"memory/lifespan.py": "from simile.memory.lifespan import lifespan\n"})


def test_server_opens_the_database_and_closes_it_on_shutdown(
    package: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SIMILE_DB", str(tmp_path / "simile.db"))
    app = create_app(package)

    with TestClient(app):
        store = memory_of(app)
        store.add(REMEMBERED)

    with pytest.raises(sqlite3.ProgrammingError):
        store.recall("mei", NOW)
    with MemoryStore(tmp_path / "simile.db") as reopened:
        assert reopened.recall("mei", NOW) == [REMEMBERED]


def test_server_keeps_a_store_already_on_app_state(package: str) -> None:
    app = create_app(package)
    injected = MemoryStore(":memory:")
    app.state.memory = injected

    with TestClient(app):
        assert memory_of(app) is injected
