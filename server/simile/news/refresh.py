import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import timedelta

from simile.news.feed import Fetched, feed_url, fetch
from simile.news.store import NewsStore
from simile.schema import NewsItem

logger = logging.getLogger(__name__)

INTERVAL = timedelta(hours=1)
MIN_GAP = timedelta(minutes=30)

type Fetch = Callable[[str, str | None, str | None], Fetched]


async def refresh(
    store: NewsStore, url: str, *, fetch: Fetch = fetch, at: float | None = None
) -> list[NewsItem]:
    """Fetch the feed at `url` once, in a thread, and store its new items. Returns them."""
    state = replace(store.feed(url), checked=time.time() if at is None else at)
    store.set_feed(url, state)
    fetched = await asyncio.to_thread(fetch, url, state.etag, state.modified)
    store.set_feed(url, replace(state, etag=fetched.etag, modified=fetched.modified))
    return store.add(fetched.items or [])


class NewsRefresher:
    """Refreshes the news every `interval` of sim time, but no sooner than `min_gap` of real time
    after the feed was last checked, even by an earlier run."""

    def __init__(
        self,
        store: NewsStore,
        url: str | None = None,
        *,
        interval: timedelta = INTERVAL,
        min_gap: timedelta = MIN_GAP,
        fetch: Fetch = fetch,
        now: Callable[[], float] = time.time,
    ) -> None:
        self.store = store
        self.url = url or feed_url()
        self.interval = interval.total_seconds()
        self.min_gap = min_gap.total_seconds()
        self.fetch = fetch
        self.now = now
        self.since = self.interval
        self.checked = store.feed(self.url).checked
        self.task: asyncio.Task[None] | None = None

    def tick(self, dt: float) -> None:
        self.since += dt
        if self.since < self.interval or self.task is not None:
            return
        now = self.now()
        if self.checked is not None and now - self.checked < self.min_gap:
            return
        self.since = 0.0
        self.checked = now
        self.task = asyncio.create_task(self._refresh(now))

    async def _refresh(self, at: float) -> None:
        try:
            added = await refresh(self.store, self.url, fetch=self.fetch, at=at)
            logger.info(f"{len(added)} new news items from {self.url}")
        except Exception:
            logger.warning(f"Couldn't refresh the news from {self.url}", exc_info=True)
        finally:
            self.task = None

    async def stop(self) -> None:
        if self.task is not None:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
