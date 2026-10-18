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
CREATE INDEX IF NOT EXISTS news_by_url ON news (json_extract(data, '$.url'));

CREATE TABLE IF NOT EXISTS news_feeds (
    url TEXT PRIMARY KEY,
    checked REAL,
    etag TEXT,
    modified TEXT
);

CREATE TABLE IF NOT EXISTS news_unanalysable (
    id TEXT NOT NULL,
    provider TEXT NOT NULL,
    PRIMARY KEY (id, provider)
);

CREATE TABLE IF NOT EXISTS news_text (
    id TEXT PRIMARY KEY,
    text TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS news_no_text (
    id TEXT PRIMARY KEY,
    reason TEXT NOT NULL
);
"""

ANALYSED = "EXISTS (SELECT 1 FROM json_each(data, '$.values'))"


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
        """Store the items whose ids and links aren't stored yet, and return them."""
        added = []
        with self._lock, self._db:
            for item in items:
                if self._db.execute(
                    "SELECT 1 FROM news WHERE json_extract(data, '$.url') = ?", (item.url,)
                ).fetchone():
                    continue
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

    def latest(
        self, n: int = 10, *, exclude: Collection[str] = (), analysed: bool | None = None
    ) -> list[NewsItem]:
        """The `n` most recently published items, newest first, leaving out the ids in
        `exclude` and, if `analysed` is given, those that are or aren't analysed."""
        where = "" if analysed is None else f" AND {'' if analysed else 'NOT '}{ANALYSED}"
        with self._lock:
            rows = self._db.execute(
                "SELECT data FROM news WHERE id NOT IN (SELECT value FROM json_each(?))"
                f"{where} ORDER BY published DESC, rowid DESC LIMIT ?",
                (json.dumps(list(exclude)), n),
            ).fetchall()
        return [NewsItem.model_validate_json(data) for (data,) in rows]

    def unanalysed(self, n: int, provider: str) -> list[NewsItem]:
        """The items among the `n` newest that aren't analysed and that `provider` hasn't
        failed to analyse, newest first."""
        with self._lock:
            rows = self._db.execute(
                "SELECT data FROM (SELECT id, data, published, rowid AS row FROM news"
                " ORDER BY published DESC, rowid DESC LIMIT ?)"
                f" WHERE NOT {ANALYSED}"
                " AND id NOT IN (SELECT id FROM news_unanalysable WHERE provider = ?)"
                " ORDER BY published DESC, row DESC",
                (n, provider),
            ).fetchall()
        return [NewsItem.model_validate_json(data) for (data,) in rows]

    def update(self, item: NewsItem) -> bool:
        """Replace the stored item that has `item`'s id, as when it's been analysed. False if
        there isn't one."""
        with self._lock, self._db:
            cursor = self._db.execute(
                "UPDATE news SET data = ? WHERE id = ?", (item.model_dump_json(), item.id)
            )
        return cursor.rowcount > 0

    def unanalysable(self, id: str, provider: str) -> None:
        """Remember that `provider` couldn't analyse the item, so it isn't asked again."""
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR IGNORE INTO news_unanalysable (id, provider) VALUES (?, ?)",
                (id, provider),
            )

    def keep_text(self, id: str, text: str) -> None:
        """Hold the article's text until its summary is written."""
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO news_text (id, text) VALUES (?, ?)", (id, text)
            )
            self._db.execute("DELETE FROM news_no_text WHERE id = ?", (id,))

    def text(self, id: str) -> str | None:
        with self._lock:
            row = self._db.execute("SELECT text FROM news_text WHERE id = ?", (id,)).fetchone()
        return row[0] if row else None

    def drop_text(self, id: str) -> None:
        with self._lock, self._db:
            self._db.execute("DELETE FROM news_text WHERE id = ?", (id,))

    def drop_texts(self, *, keep: Collection[str]) -> None:
        """Let go of the text of every article but those in `keep`."""
        with self._lock, self._db:
            self._db.execute(
                "DELETE FROM news_text WHERE id NOT IN (SELECT value FROM json_each(?))",
                (json.dumps(list(keep)),),
            )

    def no_text(self, id: str, reason: str) -> None:
        """Record why the article's text couldn't be had, so its page isn't asked for again."""
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO news_no_text (id, reason) VALUES (?, ?)", (id, reason)
            )

    def why_no_text(self, id: str) -> str | None:
        with self._lock:
            row = self._db.execute("SELECT reason FROM news_no_text WHERE id = ?", (id,)).fetchone()
        return row[0] if row else None

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
