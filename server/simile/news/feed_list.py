import logging
import os
import threading
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError
from starlette.applications import Starlette

from simile.news.config import DEFAULT_CONFIG
from simile.news.feed import FEEDS, Feed, override

logger = logging.getLogger(__name__)

FEEDS_FILE = Path(__file__).resolve().parents[2] / "data" / "feeds.json"


def feeds_file() -> Path:
    """`$SIMILE_FEEDS_FILE`, or `server/data/feeds.json`: one per install, whatever the world."""
    return Path(os.environ.get("SIMILE_FEEDS_FILE") or FEEDS_FILE)


class SavedFeed(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    url: str
    name: str = ""
    on: bool = True

    @property
    def feed(self) -> Feed:
        return Feed(self.url, self.name)


class SavedFeeds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feeds: list[SavedFeed]


DEFAULTS = tuple(SavedFeed(url=feed.url, name=feed.name) for feed in FEEDS)


class Refused(Exception):
    """A change refused, with the HTTP status and the reason in words for the player."""

    def __init__(self, status: int, reason: str) -> None:
        super().__init__(reason)
        self.status = status


class FeedList:
    """The install's feeds, saved in `path` once changed and `FEEDS` until then. Thread-safe."""

    def __init__(self, path: Path | None = None, limit: int = DEFAULT_CONFIG.max_feeds) -> None:
        self.path = path or feeds_file()
        self.limit = limit
        self._lock = threading.Lock()
        self._feeds = self._load()

    @property
    def feeds(self) -> list[SavedFeed]:
        with self._lock:
            return list(self._feeds)

    @property
    def defaults(self) -> bool:
        return tuple(self.feeds) == DEFAULTS

    def current(self) -> tuple[Feed, ...]:
        """The feeds this run reads: `$SIMILE_NEWS_FEED`'s, or else those switched on."""
        return override() or tuple(saved.feed for saved in self.feeds if saved.on)

    def check(self, url: str) -> None:
        """Refuse `url` if the list wouldn't take it."""
        with self._lock:
            self._check(url)

    def add(self, feed: SavedFeed) -> None:
        with self._lock:
            self._check(feed.url)
            self._save([*self._feeds, feed])

    def switch(self, url: str, on: bool) -> None:
        with self._lock:
            self._find(url)
            self._save(
                [f.model_copy(update={"on": on}) if f.url == url else f for f in self._feeds]
            )

    def remove(self, url: str) -> None:
        with self._lock:
            self._find(url)
            self._save([f for f in self._feeds if f.url != url])

    def reset(self) -> None:
        with self._lock:
            self.path.unlink(missing_ok=True)
            self._feeds = list(DEFAULTS)

    def _check(self, url: str) -> None:
        if any(saved.url == url for saved in self._feeds):
            raise Refused(409, "That feed is in the list already")
        if len(self._feeds) >= self.limit:
            raise Refused(
                409, f"The list takes at most {self.limit} feeds. Remove one to add another"
            )

    def _find(self, url: str) -> None:
        if not any(saved.url == url for saved in self._feeds):
            raise Refused(404, "That feed isn't in the list")

    def _load(self) -> list[SavedFeed]:
        try:
            saved = SavedFeeds.model_validate_json(self.path.read_bytes()).feeds
        except FileNotFoundError:
            return list(DEFAULTS)
        except (OSError, ValidationError) as error:
            logger.warning(f"Reading the default feeds, since {self.path} can't be read: {error}")
            return list(DEFAULTS)
        unique: dict[str, SavedFeed] = {}
        for feed in saved:
            unique.setdefault(feed.url, feed)
        return list(unique.values())

    def _save(self, feeds: list[SavedFeed]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        draft = self.path.with_name(f".{self.path.name}.tmp")
        draft.write_text(SavedFeeds(feeds=feeds).model_dump_json(indent=2) + "\n")
        draft.replace(self.path)
        self._feeds = feeds


def feeds() -> tuple[Feed, ...]:
    """The feeds a run reads now: `$SIMILE_NEWS_FEED`'s, or else the saved list's on."""
    return FeedList().current()


def feed_list_of(app: Starlette) -> FeedList:
    """The install's feed list on `app.state.feed_list`, read on first use."""
    if not hasattr(app.state, "feed_list"):
        app.state.feed_list = FeedList()
    return app.state.feed_list
