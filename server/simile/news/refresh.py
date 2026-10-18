import asyncio
import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import timedelta

from simile.news.config import DEFAULT_CONFIG, NewsConfig
from simile.news.feed import DEADLINE, Feed, FeedRefused, Fetched, fetch
from simile.news.feed_list import FeedList
from simile.news.store import NewsStore
from simile.schema import NewsItem

logger = logging.getLogger(__name__)

INTERVAL = timedelta(hours=1)
MIN_GAP = timedelta(minutes=30)
MAX_PER_FEED = 10
GIVE_UP = DEADLINE + 5

type Fetch = Callable[[Feed, str | None, str | None], Fetched]


async def fetch_in_thread(
    feed: Feed,
    etag: str | None = None,
    modified: str | None = None,
    *,
    fetch: Fetch = fetch,
    give_up: float = GIVE_UP,
) -> Fetched:
    """`fetch` in a thread, given up on after `give_up` seconds even if the thread carries on,
    as it might while the name of the feed's host resolves."""
    limit = asyncio.timeout(give_up)
    try:
        async with limit:
            return await asyncio.to_thread(fetch, feed, etag, modified)
    except TimeoutError:
        if limit.expired():
            raise TimeoutError(f"It took over {give_up:g} seconds") from None
        raise


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
    give_up: float = GIVE_UP,
) -> Refreshed:
    """Fetch `feed` once, in a thread, and store the new ones among its `limit` newest items
    that aren't too short to react to."""
    state = replace(store.feed(feed.url), checked=time.time() if at is None else at)
    store.set_feed(feed.url, state)
    fetched = await fetch_in_thread(feed, state.etag, state.modified, fetch=fetch, give_up=give_up)
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
    after it was last checked, even by an earlier run. Each feed refreshes on its own, so a slow
    or failing one holds up no other. `feeds` can be a function, asked every tick, so a feed added
    or switched on is refreshed without a restart. By default it's the saved list's."""

    def __init__(
        self,
        store: NewsStore,
        feeds: Sequence[Feed] | Callable[[], Sequence[Feed]] | None = None,
        *,
        interval: timedelta = INTERVAL,
        min_gap: timedelta = MIN_GAP,
        limit: int = MAX_PER_FEED,
        fetch: Fetch = fetch,
        now: Callable[[], float] = time.time,
        config: NewsConfig = DEFAULT_CONFIG,
    ) -> None:
        self.store = store
        if feeds is None:
            feeds = FeedList().current
        if callable(feeds):
            self.source = feeds
        else:
            chosen = tuple(feeds)
            self.source = lambda: chosen
        self.interval = interval.total_seconds()
        self.min_gap = min_gap.total_seconds()
        self.limit = limit
        self.fetch = fetch
        self.config = config
        self.now = now
        self.since: dict[str, float] = {}
        self.checked: dict[str, float | None] = {}
        self.tasks: dict[str, asyncio.Task[None]] = {}
        self._track(self.feeds)

    @property
    def feeds(self) -> tuple[Feed, ...]:
        return tuple(self.source())

    def _track(self, feeds: Sequence[Feed]) -> None:
        for feed in feeds:
            if feed.url not in self.since:
                self.since[feed.url] = self.interval
                self.checked[feed.url] = self.store.feed(feed.url).checked

    def tick(self, dt: float) -> None:
        feeds = self.feeds
        self._track(feeds)
        for url in self.since:
            self.since[url] += dt
        now = self.now()
        for feed in feeds:
            if feed.url in self.tasks or not self._due(feed.url, now):
                continue
            self.since[feed.url] = 0.0
            self.checked[feed.url] = now
            self.tasks[feed.url] = asyncio.create_task(self._refresh(feed, now))

    def _due(self, url: str, now: float) -> bool:
        checked = self.checked[url]
        return self.since[url] >= self.interval and (
            checked is None or now - checked >= self.min_gap
        )

    async def _refresh(self, feed: Feed, at: float) -> None:
        try:
            result = await refresh(
                self.store, feed, fetch=self.fetch, at=at, limit=self.limit, config=self.config
            )
        except (OSError, FeedRefused) as error:
            logger.warning(f"Couldn't refresh the news from {feed.url}: {error}")
        except Exception:
            logger.warning(f"Couldn't refresh the news from {feed.url}", exc_info=True)
        else:
            logger.info(
                f"{len(result.added)} new news items from {feed.url}, "
                f"{len(result.skipped)} skipped as too short to react to"
            )
        finally:
            del self.tasks[feed.url]

    async def stop(self) -> None:
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
