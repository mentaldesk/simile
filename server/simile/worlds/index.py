import fcntl
import logging
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

INDEX = "worlds.json"


class Entry(BaseModel):
    name: str | None = None
    made: datetime | None = None
    played: datetime | None = None


class Played(BaseModel):
    """What the folders don't say: each world's name and when it was made and last played, and
    which world was played last."""

    last: str | None = None
    worlds: dict[str, Entry] = {}

    def entry(self, id: str) -> Entry:
        return self.worlds.get(id) or Entry()


class Index:
    """`worlds.json` in the worlds' root, shared by the server and its supervisor, so every
    change holds a lock on it."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.path = root / INDEX

    def read(self) -> Played:
        if not self.path.is_file():
            return Played()
        with self._locked(fcntl.LOCK_SH):
            return self._read()

    def change(self, change: Callable[[Played], None]) -> Played:
        with self._locked(fcntl.LOCK_EX):
            played = self._read()
            change(played)
            spare = self.path.with_suffix(".tmp")
            spare.write_text(played.model_dump_json(indent=2, exclude_none=True) + "\n")
            os.replace(spare, self.path)
            return played

    def opened(self, id: str) -> None:
        """`id` is the world being played now, and the one to open next time."""

        def change(played: Played) -> None:
            played.last = id
            self._touch(played, id)

        self.change(change)

    def closed(self, id: str) -> None:
        self.change(lambda played: self._touch(played, id))

    def _touch(self, played: Played, id: str) -> None:
        played.worlds[id] = played.entry(id).model_copy(update={"played": datetime.now(UTC)})

    def _read(self) -> Played:
        try:
            return Played.model_validate_json(self.path.read_bytes())
        except FileNotFoundError:
            return Played()
        except ValidationError:
            logger.warning("Can't read %s, so starting it afresh", self.path)
            return Played()

    @contextmanager
    def _locked(self, how: int) -> Iterator[None]:
        self.root.mkdir(parents=True, exist_ok=True)
        with (self.root / f".{INDEX}.lock").open("a") as lock:
            fcntl.flock(lock, how)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
