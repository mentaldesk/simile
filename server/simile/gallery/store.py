import sqlite3
import threading
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Self

from starlette.applications import Starlette

from simile.memory import memory_of

type FrameKey = tuple[str, str]
"""A frame's map and interactable id."""

SCHEMA = """
CREATE TABLE IF NOT EXISTS paintings (
    work_id TEXT PRIMARY KEY,
    png BLOB NOT NULL,
    svg TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS hung (
    map TEXT NOT NULL,
    frame TEXT NOT NULL,
    work_id TEXT NOT NULL,
    since REAL NOT NULL,
    PRIMARY KEY (map, frame)
);
"""


class GalleryStore:
    """Every painting's picture, and which hangs in each frame, in their own tables of a SQLite
    file. Thread-safe."""

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

    def hang(
        self, work_id: str, svg: str, png: bytes, frames: Sequence[FrameKey], when: datetime
    ) -> FrameKey:
        """Store the painting and hang it in the first empty one of `frames`, or in place of the
        one hung longest ago. Paintings taken down keep their pictures."""
        if not frames:
            raise ValueError("there are no frames to hang it in")
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO paintings (work_id, png, svg) VALUES (?, ?, ?)",
                (work_id, png, svg),
            )
            since = {
                (map, frame): at
                for map, frame, at in self._db.execute("SELECT map, frame, since FROM hung")
            }
            empty = [frame for frame in frames if frame not in since]
            frame = empty[0] if empty else min(frames, key=lambda frame: since[frame])
            self._db.execute(
                "INSERT OR REPLACE INTO hung (map, frame, work_id, since) VALUES (?, ?, ?, ?)",
                (*frame, work_id, when.timestamp()),
            )
        return frame

    def hanging(self) -> dict[FrameKey, str]:
        """The work id of the painting in each frame that has one."""
        with self._lock:
            rows = self._db.execute("SELECT map, frame, work_id FROM hung").fetchall()
        return {(map, frame): work_id for map, frame, work_id in rows}

    def picture(self, work_id: str) -> bytes | None:
        """A painting's PNG."""
        with self._lock:
            row = self._db.execute(
                "SELECT png FROM paintings WHERE work_id = ?", (work_id,)
            ).fetchone()
        return row[0] if row else None


def gallery_store_of(app: Starlette) -> GalleryStore:
    """The server's gallery on `app.state.gallery_store`, opened on first use in the memory
    store's file."""
    if not hasattr(app.state, "gallery_store"):
        app.state.gallery_store = GalleryStore(memory_of(app).path)
    return app.state.gallery_store
