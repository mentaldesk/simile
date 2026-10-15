import asyncio
import logging
import threading
from datetime import UTC, datetime, timedelta

import pytest

from simile.news import FeedState, Fetched, NewsRefresher, NewsStore, parse, refresh
from simile.sim import STEP, Clock, FakeWallClock, World

URL = "https://example.com/feed"
ETAG = '"v1"'
MODIFIED = "Wed, 15 Sep 2021 20:05:26 GMT"


class FakeFeed:
    """Stands in for `fetch`: the saved feed, then unchanged once the caller has its ETag."""

    def __init__(self, xml: bytes) -> None:
        self.items = parse(xml)
        self.calls: list[tuple[str, str | None, str | None]] = []
        self.error: Exception | None = None
        self.release = threading.Event()
        self.release.set()

    def __call__(self, url: str, etag: str | None, modified: str | None) -> Fetched:
        self.calls.append((url, etag, modified))
        self.release.wait(5)
        if self.error:
            raise self.error
        if etag == ETAG:
            return Fetched(None, etag, modified)
        return Fetched(self.items, ETAG, MODIFIED)


@pytest.fixture
def feed(feed_xml: bytes) -> FakeFeed:
    return FakeFeed(feed_xml)


def village(store: NewsStore, feed: FakeFeed, speed: float) -> tuple[World, NewsRefresher]:
    world = World(Clock(datetime(2026, 1, 1, 8, tzinfo=UTC), speed=speed), FakeWallClock())
    refresher = NewsRefresher(
        store,
        URL,
        interval=timedelta(minutes=1),
        min_gap=timedelta(seconds=30),
        fetch=feed,
        now=world.loop.wall.now,
    )
    world.loop.register(refresher)
    return world, refresher


async def run(world: World, refresher: NewsRefresher, duration: timedelta) -> None:
    """Tick as the loop would, but let each refresh finish before the next tick."""
    for _ in range(round(duration.total_seconds() / STEP)):
        world.loop.wall.advance(STEP / world.clock.speed)
        world.loop.tick()
        if refresher.task is not None:
            await refresher.task


@pytest.mark.anyio
async def test_refresh_stores_new_items_and_then_asks_only_for_changes(
    store: NewsStore, feed: FakeFeed
) -> None:
    first = await refresh(store, URL, fetch=feed, at=100.0)
    second = await refresh(store, URL, fetch=feed, at=200.0)

    assert first == feed.items
    assert second == []
    assert store.latest() == feed.items
    assert feed.calls == [(URL, None, None), (URL, ETAG, MODIFIED)]
    assert store.feed(URL) == FeedState(200.0, ETAG, MODIFIED)


@pytest.mark.anyio
async def test_refresh_records_a_failed_check(store: NewsStore, feed: FakeFeed) -> None:
    feed.error = TimeoutError("timed out")

    with pytest.raises(TimeoutError):
        await refresh(store, URL, fetch=feed, at=100.0)

    assert store.feed(URL) == FeedState(checked=100.0)
    assert store.latest() == []


@pytest.mark.anyio
async def test_refreshes_at_once_then_every_interval_of_sim_time(
    store: NewsStore, feed: FakeFeed
) -> None:
    world, refresher = village(store, feed, speed=1)

    await run(world, refresher, timedelta(minutes=4, seconds=30))

    assert len(feed.calls) == 5
    assert store.latest(10) == feed.items


@pytest.mark.anyio
async def test_refreshes_no_more_than_once_per_min_gap_of_real_time(
    store: NewsStore, feed: FakeFeed
) -> None:
    world, refresher = village(store, feed, speed=10)

    await run(world, refresher, timedelta(minutes=9, seconds=10))

    assert len(feed.calls) == 2


@pytest.mark.anyio
async def test_waits_out_the_min_gap_left_by_an_earlier_run(
    store: NewsStore, feed: FakeFeed
) -> None:
    store.set_feed(URL, FeedState(checked=-10.0))
    world, refresher = village(store, feed, speed=1)

    await run(world, refresher, timedelta(seconds=19))
    assert feed.calls == []

    await run(world, refresher, timedelta(seconds=2))
    assert len(feed.calls) == 1


@pytest.mark.anyio
async def test_logs_a_failed_refresh_and_tries_again_later(
    store: NewsStore, feed: FakeFeed, caplog: pytest.LogCaptureFixture
) -> None:
    feed.error = OSError("no route to host")
    world, refresher = village(store, feed, speed=1)

    with caplog.at_level(logging.WARNING):
        await run(world, refresher, timedelta(seconds=50))
    assert len(feed.calls) == 1
    assert f"Couldn't refresh the news from {URL}" in caplog.text

    feed.error = None
    await run(world, refresher, timedelta(seconds=20))
    assert len(feed.calls) == 2
    assert store.latest(10) == feed.items


@pytest.mark.anyio
async def test_runs_one_refresh_at_a_time(store: NewsStore, feed: FakeFeed) -> None:
    feed.release.clear()
    refresher = NewsRefresher(
        store, URL, interval=timedelta(0), min_gap=timedelta(0), fetch=feed, now=lambda: 0.0
    )

    for _ in range(10):
        refresher.tick(STEP)
        await asyncio.sleep(0.001)
    feed.release.set()
    assert refresher.task is not None
    await refresher.task

    assert len(feed.calls) == 1
    assert refresher.task is None


@pytest.mark.anyio
async def test_stop_abandons_a_refresh_in_flight(store: NewsStore, feed: FakeFeed) -> None:
    feed.release.clear()
    refresher = NewsRefresher(store, URL, fetch=feed, now=lambda: 0.0)
    refresher.tick(STEP)
    while not feed.calls:
        await asyncio.sleep(0.001)

    await refresher.stop()
    feed.release.set()

    assert refresher.task is None
    assert store.latest() == []
