import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Self

from starlette.applications import Starlette

from simile.memory import memory_of
from simile.schema import Id, Key, Medium, Model, Timestamp, Work

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
CREATE TABLE IF NOT EXISTS murals (
    work_id TEXT PRIMARY KEY,
    wall TEXT NOT NULL,
    covers TEXT,
    png BLOB NOT NULL,
    svg TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS murals_by_wall ON murals (wall);
CREATE TABLE IF NOT EXISTS seeded (
    what TEXT PRIMARY KEY,
    at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS notices (
    id TEXT PRIMARY KEY,
    poster TEXT NOT NULL,
    created REAL NOT NULL,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS notices_by_poster ON notices (poster, created);
"""
SHOWING = """
SELECT w.data FROM murals m JOIN works w ON w.id = m.work_id
WHERE NOT EXISTS (SELECT 1 FROM murals c WHERE c.covers = m.work_id)
"""

NEWEST = "ORDER BY created DESC, rowid DESC"


class Notice(Model):
    """A short notice a shopkeeper puts up at the terminals: an offer, an event or an invitation.
    It isn't a work."""

    id: Key
    poster: Id
    title: str
    text: str
    created: Timestamp


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
            self._insert(work)

    def paint(self, mural: Work, svg: str, png: bytes) -> Work | None:
        """Store `mural` and its picture over whatever is on its wall, and return what that was.
        Covered murals are kept."""
        with self._lock, self._db:
            row = self._db.execute(
                f"{SHOWING} AND m.wall = ? AND m.work_id != ?", (mural.wall, mural.id)
            ).fetchone()
            covered = Work.model_validate_json(row[0]) if row else None
            self._insert(mural)
            self._db.execute(
                "INSERT OR REPLACE INTO murals (work_id, wall, covers, png, svg)"
                " VALUES (?, ?, ?, ?, ?)",
                (mural.id, mural.wall, covered.id if covered else None, png, svg),
            )
        return covered

    def showing(self) -> dict[str, Work]:
        """The mural on each painted wall, by wall id."""
        with self._lock:
            rows = self._db.execute(SHOWING).fetchall()
        murals = [Work.model_validate_json(data) for (data,) in rows]
        return {mural.wall: mural for mural in murals if mural.wall}

    def covered(self, id: str) -> Work | None:
        """The mural that `id` was painted over."""
        with self._lock:
            row = self._db.execute(
                "SELECT w.data FROM murals m JOIN works w ON w.id = m.covers WHERE m.work_id = ?",
                (id,),
            ).fetchone()
        return Work.model_validate_json(row[0]) if row else None

    def picture(self, id: str) -> bytes | None:
        """A mural's PNG."""
        with self._lock:
            row = self._db.execute("SELECT png FROM murals WHERE work_id = ?", (id,)).fetchone()
        return row[0] if row else None

    def empty(self) -> bool:
        with self._lock:
            return self._db.execute("SELECT 1 FROM works LIMIT 1").fetchone() is None

    def first_time(self, what: str, when: datetime) -> bool:
        """True the first time it's asked about `what`, which it records, and False after."""
        with self._lock, self._db:
            added = self._db.execute(
                "INSERT OR IGNORE INTO seeded (what, at) VALUES (?, ?)", (what, when.timestamp())
            )
        return added.rowcount == 1

    def svg(self, id: str) -> str | None:
        """A mural's SVG."""
        with self._lock:
            row = self._db.execute("SELECT svg FROM murals WHERE work_id = ?", (id,)).fetchone()
        return row[0] if row else None

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

    def newest(self, n: int, *, besides: Id | None = None) -> list[Work]:
        """The `n` newest works in any medium, newest first, leaving out those by `besides`."""
        return self._select(f"WHERE artist IS NOT ? {NEWEST} LIMIT ?", (besides, n))

    def oldest(self) -> Work | None:
        works = self._select("ORDER BY created, rowid LIMIT 1", ())
        return works[0] if works else None

    def post(self, notice: Notice) -> None:
        """Put `notice` up, replacing any with its id. Notices aren't works."""
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO notices (id, poster, created, data) VALUES (?, ?, ?, ?)",
                (notice.id, notice.poster, notice.created.timestamp(), notice.model_dump_json()),
            )

    def notices(self, since: datetime, n: int = -1) -> list[Notice]:
        """The `n` newest notices put up since `since`, or all of them, newest first."""
        return self._notices("WHERE created >= ?", (since.timestamp(), n))

    def last_notice(self, poster: Id) -> Notice | None:
        found = self._notices("WHERE poster = ?", (poster, 1))
        return found[0] if found else None

    def _insert(self, work: Work) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO works (id, artist, medium, created, data)"
            " VALUES (?, ?, ?, ?, ?)",
            (work.id, work.artist, work.medium, work.created.timestamp(), work.model_dump_json()),
        )

    def _notices(self, where: str, params: tuple[object, ...]) -> list[Notice]:
        with self._lock:
            rows = self._db.execute(
                f"SELECT data FROM notices {where} {NEWEST} LIMIT ?", params
            ).fetchall()
        return [Notice.model_validate_json(data) for (data,) in rows]

    def _select(self, where: str, params: tuple[object, ...]) -> list[Work]:
        with self._lock:
            rows = self._db.execute(f"SELECT data FROM works {where}", params).fetchall()
        return [Work.model_validate_json(data) for (data,) in rows]


def works_of(app: Starlette) -> WorksStore:
    """The server's works on `app.state.works`, opened on first use in the memory store's file."""
    if not hasattr(app.state, "works"):
        app.state.works = WorksStore(memory_of(app).path)
    return app.state.works
