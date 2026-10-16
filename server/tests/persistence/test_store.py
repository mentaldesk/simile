import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from simile.behaviour import Activity, Need
from simile.memory import MemoryStore
from simile.news import NewsStore
from simile.persistence import SavedNpc, SavedWorld, WorldStore
from simile.schema import Memory, NewsItem, Relationship, Tile

NOW = datetime(2026, 1, 1, 8, tzinfo=UTC)

WORLD = SavedWorld(
    now=NOW,
    npcs={
        "kofi": SavedNpc(
            position=Tile(x=32, y=12),
            activity=Activity.COFFEE_SHOP,
            target="coffee_shop",
            needs={Need.SOCIAL: 0.2, Need.CURIOSITY: 0.5, Need.REST: 0.9},
            since=NOW - timedelta(minutes=10),
            until=NOW + timedelta(minutes=5),
            cooldowns={"henrietta": NOW + timedelta(minutes=30)},
        ),
        "henrietta": SavedNpc(
            position=Tile(x=53, y=11),
            activity=Activity.WANDER,
            needs={Need.SOCIAL: 0.7, Need.CURIOSITY: 0.1, Need.REST: 0.3},
            since=NOW,
        ),
    },
)


@contextmanager
def opened(path: Path | str) -> Iterator[WorldStore]:
    with MemoryStore(path) as memory, WorldStore(memory) as store:
        yield store


def test_loads_what_it_saved_after_reopening(tmp_path: Path) -> None:
    path = tmp_path / "simile.db"
    with opened(path) as store:
        store.save(WORLD.model_copy(update={"now": NOW - timedelta(hours=1)}))
        store.save(WORLD)

    with opened(path) as reopened:
        assert reopened.load() == WORLD


def test_loads_nothing_before_the_first_save() -> None:
    with opened(":memory:") as store:
        assert store.load() is None


def test_starts_afresh_from_a_save_it_cannot_read(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "simile.db"
    with opened(path) as store:
        store.save(WORLD)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE saved_world SET data = json_set(data, '$.npcs.kofi.activity', 'nap')")

    with opened(path) as store, caplog.at_level(logging.WARNING):
        assert store.load() is None

    assert "starting afresh" in caplog.text


def test_clear_forgets_the_village_but_keeps_the_news(
    tmp_path: Path,
    relationships: list[Relationship],
    memories: list[Memory],
    news: list[NewsItem],
) -> None:
    path = tmp_path / "simile.db"
    with opened(path) as store, NewsStore(path) as headlines:
        store.memory.add(*relationships, *memories)
        headlines.add(news)
        store.save(WORLD)

        store.clear()

        assert store.load() is None
        assert store.memory.relationships("mei") == []
        assert store.memory.recall("mei", NOW, k=100) == []
        assert {item.id for item in headlines.latest(10)} == {item.id for item in news}
