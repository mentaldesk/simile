import asyncio
import logging
import socket
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
from simile.news import NewsStore, news_of, parse
from simile.news.bundled import bundled
from simile.news.config import DEFAULT_CONFIG
from simile.schema import NewsItem
from simile.sim import Clock, FakeWallClock, World, world_of
from simile.sim.headless import run_headless

MakePackage = Callable[[dict[str, str]], str]
FeedServer = Any
BUNDLED = {item.id for item in bundled()}


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


def wait_until(condition: Callable[[], object]) -> None:
    deadline = time.monotonic() + 5
    while not condition() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert condition()


def ids(items: list[NewsItem]) -> set[str]:
    return {item.id for item in items}


def listed(store: NewsStore) -> set[str]:
    return ids(store.latest(DEFAULT_CONFIG.articles))


def from_feed(store: NewsStore, feed_server: FeedServer) -> set[str]:
    return {item.id for item in store.latest(100) if item.source_url == feed_server.url}


def wait_for_feed(store: NewsStore, feed_server: FeedServer) -> None:
    wait_until(lambda: len(from_feed(store, feed_server)) == 5)


@pytest.fixture
def news_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SIMILE_NEWS")


def test_leaves_the_news_alone_when_news_is_off(package: str, feed_server: FeedServer) -> None:
    app = create_app(package)

    with TestClient(app):
        wait_for_ticks(app)
        assert news_of(app).latest() == []

    assert feed_server.requests == []


def test_runs_headless_without_fetching_when_news_is_off(
    package: str, feed_server: FeedServer
) -> None:
    world = World(Clock(datetime(2026, 1, 1, 8, tzinfo=UTC)), FakeWallClock())

    asyncio.run(run_headless(world, timedelta(minutes=5), package))

    assert feed_server.requests == []


def test_the_whole_server_fetches_nothing_with_the_tests_settings(
    feed_server: FeedServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[object] = []
    monkeypatch.setattr("simile.news.feed.urlopen", lambda *args, **_: opened.append(args))
    app = create_app()

    with TestClient(app):
        wait_for_ticks(app)

    assert opened == []
    assert feed_server.requests == []


@pytest.mark.usefixtures("news_on")
def test_fetches_into_the_memory_database_by_default(
    package: str, feed_server: FeedServer, database: Path
) -> None:
    app = create_app(package)

    with TestClient(app):
        store = news_of(app)
        wait_for_feed(store, feed_server)

    with pytest.raises(sqlite3.ProgrammingError):
        store.latest()
    with NewsStore(database) as reopened:
        assert len(from_feed(reopened, feed_server)) == 5
        assert reopened.feed(feed_server.url).etag == feed_server.etag
    assert len(feed_server.requests) == 1


@pytest.mark.usefixtures("news_on")
def test_a_restart_waits_out_the_min_gap(
    package: str, feed_server: FeedServer, database: Path
) -> None:
    first = create_app(package)
    with TestClient(first):
        wait_for_feed(news_of(first), feed_server)
        stored = ids(news_of(first).latest(100))

    second = create_app(package)
    with TestClient(second):
        wait_for_ticks(second)
        assert ids(news_of(second).latest(100)) == stored

    assert len(feed_server.requests) == 1


@pytest.mark.usefixtures("news_on")
def test_lists_the_bundled_articles_until_the_first_fetch_is_in(
    package: str, feed_server: FeedServer, database: Path, caplog: pytest.LogCaptureFixture
) -> None:
    feed_server.gate.clear()
    app = create_app(package)

    with caplog.at_level(logging.INFO, logger="simile.news.lifespan"), TestClient(app):
        store = news_of(app)
        wait_until(lambda: feed_server.requests)
        assert listed(store) == BUNDLED
        feed_server.gate.set()
        wait_for_feed(store, feed_server)
        assert ids(store.latest(100)) == BUNDLED | from_feed(store, feed_server)

    assert [r.getMessage() for r in caplog.records if r.name == "simile.news.lifespan"] == [
        f"No news stored yet, so the terminals list {len(BUNDLED)} bundled articles until the "
        "feeds' are in"
    ]


@pytest.mark.usefixtures("news_on")
def test_lists_the_bundled_articles_when_the_feeds_cant_be_reached(
    package: str, database: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    with socket.socket() as closed:
        closed.bind(("127.0.0.1", 0))
        port = closed.getsockname()[1]
    monkeypatch.setenv("SIMILE_NEWS_FEED", f"http://127.0.0.1:{port}/feed")
    app = create_app(package)

    with caplog.at_level(logging.WARNING, logger="simile.news.refresh"), TestClient(app):
        wait_until(lambda: any("Couldn't refresh" in r.getMessage() for r in caplog.records))
        assert listed(news_of(app)) == BUNDLED


@pytest.mark.usefixtures("news_on")
def test_adds_no_bundled_articles_to_news_already_stored(
    package: str, feed_server: FeedServer, database: Path, feed_xml: bytes
) -> None:
    with NewsStore(database) as store:
        store.add(parse(feed_xml))
    app = create_app(package)

    with TestClient(app):
        wait_until(lambda: feed_server.requests)
        assert len(news_of(app).latest(100)) == 5


def test_leaves_news_the_canned_llm_cant_analyse_unanalysed_and_says_so_once(
    make_package: MakePackage,
    database: Path,
    feed_xml: bytes,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with NewsStore(database) as store:
        store.add(parse(feed_xml))
    package = make_package(
        {
            "llm/lifespan.py": "from simile.llm.lifespan import lifespan\n",
            "memory/lifespan.py": "from simile.memory.lifespan import lifespan\n",
            "news/lifespan.py": "from simile.news.lifespan import lifespan\n",
            "sim/lifespan.py": "from simile.sim.lifespan import running\n",
        }
    )
    app = create_app(package)

    with caplog.at_level(logging.DEBUG, logger="simile.news.analysis"), TestClient(app):
        deadline = time.monotonic() + 5
        while news_of(app).unanalysed(60, "canned") and time.monotonic() < deadline:
            time.sleep(0.01)

    with NewsStore(database) as store:
        assert store.unanalysed(60, "canned") == []
        assert len(store.unanalysed(60, "claude-code")) == 5
        assert store.latest(analysed=True) == []
    failures = [r for r in caplog.records if "couldn't analyse" in r.getMessage()]
    assert [r.levelno for r in failures] == [logging.WARNING] + [logging.DEBUG] * 4
