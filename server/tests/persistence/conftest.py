from pathlib import Path

import pytest
from pydantic import TypeAdapter

from simile.schema import Memory, Model, NewsItem, Relationship

FIXTURES = Path(__file__).parents[1] / "fixtures"


def load[T: Model](name: str, model: type[T]) -> list[T]:
    return TypeAdapter(list[model]).validate_json((FIXTURES / name).read_bytes())


@pytest.fixture
def database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A database file for `SIMILE_DB`, in place of the tests' in-memory one."""
    path = tmp_path / "data" / "simile.db"
    monkeypatch.setenv("SIMILE_DB", str(path))
    return path


@pytest.fixture
def relationships() -> list[Relationship]:
    return load("relationships.json", Relationship)


@pytest.fixture
def memories() -> list[Memory]:
    return load("memories.json", Memory)


@pytest.fixture
def news() -> list[NewsItem]:
    return load("news_items.json", NewsItem)
