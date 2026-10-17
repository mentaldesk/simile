import sqlite3
import threading
from pathlib import Path
from types import TracebackType
from typing import Self

from starlette.applications import Starlette

from simile.memory import memory_of
from simile.schema import Id, Medium, Work

SCHEMA = """
CREATE TABLE IF NOT EXISTS works (
    id TEXT PRIMARY KEY,
    artist TEXT NOT NULL,
    medium TEXT NOT NULL,
    created REAL NOT NULL,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS works_by_medium ON works (medium, created);
CREATE INDEX IF NOT EXISTS works_by_artist ON works (artist, created);
"""

NEWEST = "ORDER BY created DESC, rowid DESC"


class WorksStore:
    """The residents' works, in their own table of a SQLite file. Thread-safe."""

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

    def add(self, work: Work) -> None:
        """Store `work`, replacing any with its id."""
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO works (id, artist, medium, created, data)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    work.id,
                    work.artist,
                    work.medium,
                    work.created.timestamp(),
                    work.model_dump_json(),
                ),
            )

    def get(self, id: str) -> Work | None:
        with self._lock:
            row = self._db.execute("SELECT data FROM works WHERE id = ?", (id,)).fetchone()
        return Work.model_validate_json(row[0]) if row else None

    def latest(self, medium: Medium, n: int = 10) -> list[Work]:
        """The `n` newest works in `medium`, newest first."""
        return self._select(f"WHERE medium = ? {NEWEST} LIMIT ?", (medium, n))

    def by(self, artist: Id, n: int = -1) -> list[Work]:
        """`artist`'s works, newest first: the `n` newest, or all of them."""
        return self._select(f"WHERE artist = ? {NEWEST} LIMIT ?", (artist, n))

    def _select(self, where: str, params: tuple[object, ...]) -> list[Work]:
        with self._lock:
            rows = self._db.execute(f"SELECT data FROM works {where}", params).fetchall()
        return [Work.model_validate_json(data) for (data,) in rows]


def works_of(app: Starlette) -> WorksStore:
    """The server's works on `app.state.works`, opened on first use in the memory store's file."""
    if not hasattr(app.state, "works"):
        app.state.works = WorksStore(memory_of(app).path)
    return app.state.works
