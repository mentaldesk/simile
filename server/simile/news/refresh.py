import asyncio
import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import timedelta

from simile.news.config import DEFAULT_CONFIG, NewsConfig
from simile.news.feed import Feed, Fetched, fetch
from simile.news.feed import feeds as configured_feeds
from simile.news.store import NewsStore
from simile.schema import NewsItem

logger = logging.getLogger(__name__)

INTERVAL = timedelta(hours=1)
MIN_GAP = timedelta(minutes=30)
MAX_PER_FEED = 10

type Fetch = Callable[[Feed, str | None, str | None], Fetched]


@dataclass(frozen=True)
class Refreshed:
    """The items a refresh stored, and the feed's items it skipped as too short to react to."""

    added: list[NewsItem]
    skipped: list[NewsItem]


def too_short(item: NewsItem, config: NewsConfig = DEFAULT_CONFIG) -> bool:
    return len(item.summary.split()) < config.min_summary_words


async def refresh(
    store: NewsStore,
    feed: Feed,
    *,
    fetch: Fetch = fetch,
    at: float | None = None,
    limit: int = MAX_PER_FEED,
    config: NewsConfig = DEFAULT_CONFIG,
) -> Refreshed:
    """Fetch `feed` once, in a thread, and store the new ones among its `limit` newest items
    that aren't too short to react to."""
    state = replace(store.feed(feed.url), checked=time.time() if at is None else at)
    store.set_feed(feed.url, state)
    fetched = await asyncio.to_thread(fetch, feed, state.etag, state.modified)
    store.set_feed(feed.url, replace(state, etag=fetched.etag, modified=fetched.modified))
    items = fetched.items or []
    skipped = [item for item in items if too_short(item, config)]
    if skipped:
        titles = ", ".join(repr(item.title) for item in skipped)
        logger.debug(f"Skipped as too short to react to from {feed.url}: {titles}")
    kept = [item for item in items if not too_short(item, config)]
    newest = sorted(kept, key=lambda item: item.published, reverse=True)
    return Refreshed(store.add(newest[:limit]), skipped)


async def refresh_all(
    store: NewsStore,
    feeds: Sequence[Feed],
    *,
    fetch: Fetch = fetch,
    at: float | None = None,
    limit: int = MAX_PER_FEED,
    config: NewsConfig = DEFAULT_CONFIG,
) -> list[Refreshed | BaseException]:
    """Refresh every feed at once. A feed that fails gives its exception in place of what it
    refreshed, and doesn't stop the others."""
    return await asyncio.gather(
        *(refresh(store, feed, fetch=fetch, at=at, limit=limit, config=config) for feed in feeds),
        return_exceptions=True,
    )


class NewsRefresher:
    """Refreshes each feed every `interval` of sim time, but no sooner than `min_gap` of real time
    after it was last checked, even by an earlier run."""

    def __init__(
        self,
        store: NewsStore,
        feeds: Sequence[Feed] | None = None,
        *,
        interval: timedelta = INTERVAL,
        min_gap: timedelta = MIN_GAP,
        limit: int = MAX_PER_FEED,
        fetch: Fetch = fetch,
        now: Callable[[], float] = time.time,
        config: NewsConfig = DEFAULT_CONFIG,
    ) -> None:
        self.store = store
        self.feeds = tuple(feeds) if feeds is not None else configured_feeds()
        self.interval = interval.total_seconds()
        self.min_gap = min_gap.total_seconds()
        self.limit = limit
        self.fetch = fetch
        self.config = config
        self.now = now
        self.since = {feed.url: self.interval for feed in self.feeds}
        self.checked = {feed.url: store.feed(feed.url).checked for feed in self.feeds}
        self.task: asyncio.Task[None] | None = None

    def tick(self, dt: float) -> None:
        for url in self.since:
            self.since[url] += dt
        if self.task is not None:
            return
        now = self.now()
        due = [feed for feed in self.feeds if self._due(feed.url, now)]
        if not due:
            return
        for feed in due:
            self.since[feed.url] = 0.0
            self.checked[feed.url] = now
        self.task = asyncio.create_task(self._refresh(due, now))

    def _due(self, url: str, now: float) -> bool:
        checked = self.checked[url]
        return self.since[url] >= self.interval and (
            checked is None or now - checked >= self.min_gap
        )

    async def _refresh(self, feeds: Sequence[Feed], at: float) -> None:
        try:
            results = await refresh_all(
                self.store, feeds, fetch=self.fetch, at=at, limit=self.limit, config=self.config
            )
            for feed, result in zip(feeds, results, strict=True):
                if isinstance(result, OSError):
                    logger.warning(f"Couldn't refresh the news from {feed.url}: {result}")
                elif isinstance(result, BaseException):
                    logger.warning(f"Couldn't refresh the news from {feed.url}", exc_info=result)
                else:
                    logger.info(
                        f"{len(result.added)} new news items from {feed.url}, "
                        f"{len(result.skipped)} skipped as too short to react to"
                    )
        finally:
            self.task = None

    async def stop(self) -> None:
        if self.task is not None:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
