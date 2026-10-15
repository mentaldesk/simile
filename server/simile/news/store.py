import json
import sqlite3
import threading
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Self

from starlette.applications import Starlette

from simile.memory import memory_of
from simile.schema import NewsItem

SCHEMA = """
CREATE TABLE IF NOT EXISTS news (
    id TEXT PRIMARY KEY,
    published REAL NOT NULL,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS news_by_published ON news (published);

CREATE TABLE IF NOT EXISTS news_feeds (
    url TEXT PRIMARY KEY,
    checked REAL,
    etag TEXT,
    modified TEXT
);
"""


@dataclass(frozen=True)
class FeedState:
    """When a feed was last checked, in Unix time, and its validators for a conditional GET."""

    checked: float | None = None
    etag: str | None = None
    modified: str | None = None


class NewsStore:
    """News items and the feeds they came from, in their own tables of a SQLite file.
    Thread-safe."""

    def __init__(self, path: str | Path) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.executescript(SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def add(self, items: Iterable[NewsItem]) -> list[NewsItem]:
        """Store the items whose ids aren't stored yet, and return them."""
        added = []
        with self._lock, self._db:
            for item in items:
                cursor = self._db.execute(
                    "INSERT INTO news (id, published, data) VALUES (?, ?, ?)"
                    " ON CONFLICT (id) DO NOTHING",
                    (item.id, item.published.timestamp(), item.model_dump_json()),
                )
                if cursor.rowcount:
                    added.append(item)
        return added

    def get(self, id: str) -> NewsItem | None:
        with self._lock:
            row = self._db.execute("SELECT data FROM news WHERE id = ?", (id,)).fetchone()
        return NewsItem.model_validate_json(row[0]) if row else None

    def latest(self, n: int = 10, *, exclude: Collection[str] = ()) -> list[NewsItem]:
        """The `n` most recently published items, newest first, leaving out the ids in
        `exclude`."""
        with self._lock:
            rows = self._db.execute(
                "SELECT data FROM news WHERE id NOT IN (SELECT value FROM json_each(?))"
                " ORDER BY published DESC, rowid DESC LIMIT ?",
                (json.dumps(list(exclude)), n),
            ).fetchall()
        return [NewsItem.model_validate_json(data) for (data,) in rows]

    def feed(self, url: str) -> FeedState:
        with self._lock:
            row = self._db.execute(
                "SELECT checked, etag, modified FROM news_feeds WHERE url = ?", (url,)
            ).fetchone()
        return FeedState(*row) if row else FeedState()

    def set_feed(self, url: str, state: FeedState) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO news_feeds (url, checked, etag, modified)"
                " VALUES (?, ?, ?, ?)",
                (url, state.checked, state.etag, state.modified),
            )


def news_of(app: Starlette) -> NewsStore:
    """The server's news on `app.state.news`, opened on first use in the memory store's file."""
    if not hasattr(app.state, "news"):
        app.state.news = NewsStore(memory_of(app).path)
    return app.state.news
