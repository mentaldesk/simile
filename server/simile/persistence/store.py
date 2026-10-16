import logging
import sqlite3
import threading
from types import TracebackType
from typing import Self

from pydantic import ValidationError

from simile.memory import MemoryStore
from simile.persistence.state import SavedWorld

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS saved_world (
    id INTEGER PRIMARY KEY CHECK (id = 0),
    data TEXT NOT NULL
);
"""


class WorldStore:
    """The saved world, in its own table of R2's database file. Thread-safe."""

    def __init__(self, memory: MemoryStore) -> None:
        self.memory = memory
        self.path = memory.path
        self._lock = threading.Lock()
        self._db = sqlite3.connect(memory.path, check_same_thread=False)
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

    def save(self, world: SavedWorld) -> None:
        data = world.model_dump_json()
        with self._lock, self._db:
            self._db.execute("INSERT OR REPLACE INTO saved_world (id, data) VALUES (0, ?)", (data,))

    def load(self) -> SavedWorld | None:
        """The last world saved, or None if there isn't one this version can read."""
        with self._lock:
            row = self._db.execute("SELECT data FROM saved_world").fetchone()
        if row is None:
            return None
        try:
            return SavedWorld.model_validate_json(row[0])
        except ValidationError:
            logger.warning("Can't read the world saved in %s, so starting afresh", self.path)
            return None

    def clear(self) -> None:
        """Forget the village: the saved world and everything R2 holds. The news stays."""
        self.memory.clear()
        with self._lock, self._db:
            self._db.execute("DELETE FROM saved_world")
