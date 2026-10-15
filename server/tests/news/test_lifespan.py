import asyncio
import sqlite3
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.app import create_app
from simile.news import NewsStore, news_of
from simile.sim import Clock, FakeWallClock, World, world_of
from simile.sim.headless import run_headless

MakePackage = Callable[[dict[str, str]], str]
FeedServer = Any


class TickCounter:
    def __init__(self, ticks: int) -> None:
        self.left = ticks
        self.done = threading.Event()

    def tick(self, dt: float) -> None:
        self.left -= 1
        if self.left <= 0:
            self.done.set()


@pytest.fixture
def package(make_package: MakePackage) -> str:
    return make_package(
        {
            "memory/lifespan.py": "from simile.memory.lifespan import lifespan\n",
            "news/lifespan.py": "from simile.news.lifespan import lifespan\n",
            "sim/lifespan.py": "from simile.sim.lifespan import running\n",
        }
    )


@pytest.fixture
def database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "simile.db"
    monkeypatch.setenv("SIMILE_DB", str(path))
    return path


@pytest.fixture(autouse=True)
def local_feed(feed_server: FeedServer, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIMILE_NEWS_FEED", feed_server.url)


def wait_for_ticks(app: Starlette, ticks: int = 3) -> None:
    counter = TickCounter(ticks)
    world_of(app).loop.register(counter)
    assert counter.done.wait(5)


def wait_for_news(app: Starlette) -> None:
    deadline = time.monotonic() + 5
    while not news_of(app).latest() and time.monotonic() < deadline:
        time.sleep(0.01)


def test_serves_stored_news_without_fetching_by_default(
    package: str, feed_server: FeedServer
) -> None:
    app = create_app(package)

    with TestClient(app):
        wait_for_ticks(app)
        assert news_of(app).latest() == []

    assert feed_server.requests == []


def test_runs_headless_without_fetching_by_default(package: str, feed_server: FeedServer) -> None:
    world = World(Clock(datetime(2026, 1, 1, 8, tzinfo=UTC)), FakeWallClock())

    asyncio.run(run_headless(world, timedelta(minutes=5), package))

    assert feed_server.requests == []


def test_refreshes_into_the_memory_database_when_asked(
    package: str, feed_server: FeedServer, database: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SIMILE_NEWS", "1")
    app = create_app(package)

    with TestClient(app):
        store = news_of(app)
        wait_for_news(app)
        assert len(store.latest()) == 5

    with pytest.raises(sqlite3.ProgrammingError):
        store.latest()
    with NewsStore(database) as reopened:
        assert len(reopened.latest()) == 5
        assert reopened.feed(feed_server.url).etag == feed_server.etag
    assert len(feed_server.requests) == 1


def test_a_restart_waits_out_the_min_gap(
    package: str, feed_server: FeedServer, database: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SIMILE_NEWS", "1")
    first = create_app(package)
    with TestClient(first):
        wait_for_news(first)

    second = create_app(package)
    with TestClient(second):
        wait_for_ticks(second)
        assert len(news_of(second).latest()) == 5

    assert len(feed_server.requests) == 1
