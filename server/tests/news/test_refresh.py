import asyncio
import logging
import threading
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from simile.news import (
    Feed,
    FeedState,
    Fetched,
    NewsRefresher,
    NewsStore,
    parse,
    refresh,
    refresh_all,
)
from simile.news.config import NewsConfig
from simile.news.refresh import MAX_PER_FEED, Refreshed
from simile.schema import NewsItem
from simile.sim import STEP, Clock, FakeWallClock, World

FIXTURES = Path(__file__).parent / "fixtures"
FEED = Feed("https://example.com/feed", "Example")
OPENAI = Feed("https://openai.com/news/rss.xml", "OpenAI")
RNZ = Feed("https://www.rnz.co.nz/rss/sport.xml", "RNZ Sport")
ECONOMIST = Feed("https://www.economist.com/the-world-this-week/rss.xml", "The Economist")
ETAG = '"v1"'
MODIFIED = "Wed, 15 Sep 2021 20:05:26 GMT"


class FakeFeeds:
    """Stands in for `fetch`: each feed's items, then unchanged once the caller has its ETag."""

    def __init__(self, items: dict[Feed, list[NewsItem]]) -> None:
        self.items = items
        self.calls: list[tuple[str, str | None, str | None]] = []
        self.errors: dict[Feed, Exception] = {}
        self.release = threading.Event()
        self.release.set()

    def __call__(self, feed: Feed, etag: str | None, modified: str | None) -> Fetched:
        self.calls.append((feed.url, etag, modified))
        self.release.wait(5)
        if feed in self.errors:
            raise self.errors[feed]
        if etag == ETAG:
            return Fetched(None, etag, modified)
        return Fetched(self.items[feed], ETAG, MODIFIED)

    def urls(self) -> list[str]:
        return sorted(url for url, _, _ in self.calls)


def saved(name: str, feed: Feed) -> list[NewsItem]:
    return parse((FIXTURES / name).read_bytes(), feed)


def story(
    id: str, day: int, feed: Feed, url: str | None = None, summary: str = "Something happened here."
) -> NewsItem:
    return NewsItem(
        id=id,
        title=f"Story {id}",
        url=url or f"https://example.com/{id}",
        summary=summary,
        published=datetime(2026, 10, day, tzinfo=UTC),
        source=feed.name,
        source_url=feed.url,
    )


@pytest.fixture
def feed(feed_xml: bytes) -> FakeFeeds:
    return FakeFeeds({FEED: parse(feed_xml, FEED)})


@pytest.fixture
def two_feeds() -> FakeFeeds:
    return FakeFeeds({OPENAI: saved("openai.xml", OPENAI), RNZ: saved("rnz.xml", RNZ)})


def village(
    store: NewsStore, fake: FakeFeeds, speed: float, feeds: Sequence[Feed] = (FEED,)
) -> tuple[World, NewsRefresher]:
    world = World(Clock(datetime(2026, 1, 1, 8, tzinfo=UTC), speed=speed), FakeWallClock())
    refresher = NewsRefresher(
        store,
        feeds,
        interval=timedelta(minutes=1),
        min_gap=timedelta(seconds=30),
        fetch=fake,
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
    store: NewsStore, feed: FakeFeeds
) -> None:
    first = await refresh(store, FEED, fetch=feed, at=100.0)
    second = await refresh(store, FEED, fetch=feed, at=200.0)

    assert first == Refreshed(feed.items[FEED], [])
    assert second == Refreshed([], [])
    assert store.latest() == feed.items[FEED]
    assert feed.calls == [(FEED.url, None, None), (FEED.url, ETAG, MODIFIED)]
    assert store.feed(FEED.url) == FeedState(200.0, ETAG, MODIFIED)


@pytest.mark.anyio
async def test_refresh_records_a_failed_check(store: NewsStore, feed: FakeFeeds) -> None:
    feed.errors[FEED] = TimeoutError("timed out")

    with pytest.raises(TimeoutError):
        await refresh(store, FEED, fetch=feed, at=100.0)

    assert store.feed(FEED.url) == FeedState(checked=100.0)
    assert store.latest() == []


@pytest.mark.anyio
async def test_refresh_takes_only_the_newest_items_of_a_long_feed(
    store: NewsStore, two_feeds: FakeFeeds
) -> None:
    everything = two_feeds.items[OPENAI]

    added = (await refresh(store, OPENAI, fetch=two_feeds)).added

    newest = sorted(everything, key=lambda item: item.published, reverse=True)
    assert len(everything) > MAX_PER_FEED
    assert added == newest[:MAX_PER_FEED]
    assert sorted(item.id for item in store.latest(100)) == sorted(item.id for item in added)


@pytest.mark.anyio
async def test_refresh_caps_by_date_not_feed_order(store: NewsStore) -> None:
    fake = FakeFeeds({FEED: [story(f"day-{day}", day, FEED) for day in (3, 1, 2, 5, 4)]})

    refreshed = await refresh(store, FEED, fetch=fake, limit=2)

    assert [item.id for item in refreshed.added] == ["day-5", "day-4"]


@pytest.mark.anyio
async def test_refresh_skips_header_items_and_keeps_the_feeds_articles(store: NewsStore) -> None:
    fake = FakeFeeds({ECONOMIST: saved("economist.xml", ECONOMIST)})

    refreshed = await refresh(store, ECONOMIST, fetch=fake)

    assert sorted(item.title for item in refreshed.skipped) == ["Business"] * 4 + ["Politics"] * 4
    assert [item.title for item in refreshed.added] == [
        "Cartoon: AI tsunami",
        "Cartoon: America’s gargantuan debt",
        "Cartoon: Democracy v autocracy",
        "Cartoon: The evolution of modern warfare",
        "Cover Story newsletter: Can the AI arms race be stopped?",
    ]
    assert store.latest(100) == refreshed.added


@pytest.mark.anyio
async def test_refresh_skips_summaries_too_short_before_capping(store: NewsStore) -> None:
    summaries = {5: "", 4: "Three words here.", 3: "Read more.", 2: "Long enough summary.", 1: "Ok"}
    fake = FakeFeeds({FEED: [story(f"day-{d}", d, FEED, summary=s) for d, s in summaries.items()]})

    refreshed = await refresh(store, FEED, fetch=fake, limit=2)

    assert [item.id for item in refreshed.added] == ["day-4", "day-2"]
    assert [item.id for item in refreshed.skipped] == ["day-5", "day-3", "day-1"]


@pytest.mark.anyio
async def test_the_word_threshold_is_configurable(store: NewsStore) -> None:
    fake = FakeFeeds({ECONOMIST: saved("economist.xml", ECONOMIST)})

    refreshed = await refresh(
        store, ECONOMIST, fetch=fake, limit=100, config=NewsConfig(min_summary_words=0)
    )

    assert (len(refreshed.added), refreshed.skipped) == (13, [])


@pytest.mark.anyio
async def test_refresh_all_reads_every_feed(store: NewsStore, two_feeds: FakeFeeds) -> None:
    openai, rnz = await refresh_all(store, [OPENAI, RNZ], fetch=two_feeds, at=100.0)

    assert isinstance(openai, Refreshed) and isinstance(rnz, Refreshed)
    assert (len(openai.added), len(rnz.added)) == (MAX_PER_FEED, MAX_PER_FEED)
    stored = store.latest(100)
    assert {item.source for item in stored} == {"OpenAI", "RNZ Sport"}
    assert sorted(item.id for item in stored) == sorted(
        item.id for item in openai.added + rnz.added
    )
    assert two_feeds.urls() == sorted([OPENAI.url, RNZ.url])
    assert store.feed(RNZ.url) == FeedState(100.0, ETAG, MODIFIED)


@pytest.mark.anyio
async def test_refresh_all_carries_on_past_a_failing_feed(
    store: NewsStore, two_feeds: FakeFeeds
) -> None:
    two_feeds.errors[OPENAI] = OSError("no route to host")

    openai, rnz = await refresh_all(store, [OPENAI, RNZ], fetch=two_feeds)

    assert isinstance(openai, OSError)
    assert isinstance(rnz, Refreshed) and len(rnz.added) == MAX_PER_FEED
    assert {item.source for item in store.latest(100)} == {"RNZ Sport"}


@pytest.mark.anyio
async def test_refresh_all_stores_a_story_two_feeds_carry_once(store: NewsStore) -> None:
    shared = story("shared", 5, OPENAI)
    fake = FakeFeeds(
        {
            OPENAI: [shared, story("openai-only", 4, OPENAI)],
            RNZ: [
                shared.model_copy(update={"source": RNZ.name, "source_url": RNZ.url}),
                story("relinked", 3, RNZ, url="https://example.com/openai-only"),
                story("rnz-only", 2, RNZ),
            ],
        }
    )

    await refresh_all(store, [OPENAI, RNZ], fetch=fake)

    stored = store.latest(100)
    assert len(stored) == 3
    assert {item.url for item in stored} == {
        "https://example.com/shared",
        "https://example.com/openai-only",
        "https://example.com/rnz-only",
    }


@pytest.mark.anyio
async def test_refreshes_at_once_then_every_interval_of_sim_time(
    store: NewsStore, feed: FakeFeeds
) -> None:
    world, refresher = village(store, feed, speed=1)

    await run(world, refresher, timedelta(minutes=4, seconds=30))

    assert len(feed.calls) == 5
    assert store.latest(10) == feed.items[FEED]


@pytest.mark.anyio
async def test_refreshes_no_more_than_once_per_min_gap_of_real_time(
    store: NewsStore, feed: FakeFeeds
) -> None:
    world, refresher = village(store, feed, speed=10)

    await run(world, refresher, timedelta(minutes=9, seconds=10))

    assert len(feed.calls) == 2


@pytest.mark.anyio
async def test_waits_out_the_min_gap_left_by_an_earlier_run(
    store: NewsStore, feed: FakeFeeds
) -> None:
    store.set_feed(FEED.url, FeedState(checked=-10.0))
    world, refresher = village(store, feed, speed=1)

    await run(world, refresher, timedelta(seconds=19))
    assert feed.calls == []

    await run(world, refresher, timedelta(seconds=2))
    assert len(feed.calls) == 1


@pytest.mark.anyio
async def test_keeps_each_feeds_min_gap_apart(store: NewsStore, two_feeds: FakeFeeds) -> None:
    store.set_feed(RNZ.url, FeedState(checked=-10.0))
    world, refresher = village(store, two_feeds, speed=1, feeds=[OPENAI, RNZ])

    await run(world, refresher, timedelta(seconds=19))
    assert two_feeds.urls() == [OPENAI.url]

    await run(world, refresher, timedelta(seconds=2))
    assert two_feeds.urls() == sorted([OPENAI.url, RNZ.url])


@pytest.mark.anyio
async def test_logs_a_failed_refresh_and_tries_again_later(
    store: NewsStore, feed: FakeFeeds, caplog: pytest.LogCaptureFixture
) -> None:
    feed.errors[FEED] = OSError("no route to host")
    world, refresher = village(store, feed, speed=1)

    with caplog.at_level(logging.WARNING):
        await run(world, refresher, timedelta(seconds=50))
    assert len(feed.calls) == 1
    assert f"Couldn't refresh the news from {FEED.url}" in caplog.text

    del feed.errors[FEED]
    await run(world, refresher, timedelta(seconds=20))
    assert len(feed.calls) == 2
    assert store.latest(10) == feed.items[FEED]


@pytest.mark.anyio
async def test_logs_what_each_feed_skipped(
    store: NewsStore, two_feeds: FakeFeeds, caplog: pytest.LogCaptureFixture
) -> None:
    two_feeds.items[ECONOMIST] = saved("economist.xml", ECONOMIST)
    world, refresher = village(store, two_feeds, speed=1, feeds=[ECONOMIST, RNZ])

    with caplog.at_level(logging.DEBUG, logger="simile.news.refresh"):
        await run(world, refresher, timedelta(seconds=1))

    assert (
        f"5 new news items from {ECONOMIST.url}, 8 skipped as too short to react to" in caplog.text
    )
    assert f"10 new news items from {RNZ.url}, 0 skipped" in caplog.text
    assert f"from {ECONOMIST.url}: 'Politics', 'Business', 'Business'" in caplog.text


@pytest.mark.anyio
async def test_one_failing_feed_doesnt_stop_the_others(
    store: NewsStore, two_feeds: FakeFeeds, caplog: pytest.LogCaptureFixture
) -> None:
    two_feeds.errors[RNZ] = TimeoutError("timed out")
    world, refresher = village(store, two_feeds, speed=1, feeds=[OPENAI, RNZ])

    with caplog.at_level(logging.WARNING):
        await run(world, refresher, timedelta(seconds=1))

    assert two_feeds.urls() == sorted([OPENAI.url, RNZ.url])
    assert {item.source for item in store.latest(100)} == {"OpenAI"}
    assert f"Couldn't refresh the news from {RNZ.url}" in caplog.text
    assert OPENAI.url not in caplog.text


@pytest.mark.anyio
async def test_runs_one_refresh_at_a_time(store: NewsStore, feed: FakeFeeds) -> None:
    feed.release.clear()
    refresher = NewsRefresher(
        store, [FEED], interval=timedelta(0), min_gap=timedelta(0), fetch=feed, now=lambda: 0.0
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
async def test_stop_abandons_a_refresh_in_flight(store: NewsStore, feed: FakeFeeds) -> None:
    feed.release.clear()
    refresher = NewsRefresher(store, [FEED], fetch=feed, now=lambda: 0.0)
    refresher.tick(STEP)
    while not feed.calls:
        await asyncio.sleep(0.001)

    await refresher.stop()
    feed.release.set()

    assert refresher.task is None
    assert store.latest() == []


def test_refreshes_the_configured_feeds_by_default(
    store: NewsStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SIMILE_NEWS_FEED", f"{RNZ.url},https://example.com/feed")

    assert NewsRefresher(store).feeds == (RNZ, Feed("https://example.com/feed"))
