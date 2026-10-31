import json
import logging
import os
import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from types import TracebackType
from typing import Any, Self

from starlette.applications import Starlette

from simile.schema import Flag, InteractionEvent, Memory, MemoryKind, Relationship

logger = logging.getLogger(__name__)

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "simile.db"
HALF_LIFE = timedelta(hours=12)

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    actor TEXT NOT NULL,
    target TEXT NOT NULL,
    time REAL NOT NULL,
    magnitude REAL NOT NULL,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_by_pair ON events (actor, target);

CREATE TABLE IF NOT EXISTS flags (
    owner TEXT NOT NULL,
    about TEXT NOT NULL,
    id TEXT NOT NULL,
    created REAL NOT NULL,
    resolved REAL,
    data TEXT NOT NULL,
    PRIMARY KEY (owner, about, id)
);

CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY,
    owner TEXT NOT NULL,
    kind TEXT NOT NULL,
    time REAL NOT NULL,
    salience REAL NOT NULL,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS memories_by_owner ON memories (owner, kind);

CREATE TABLE IF NOT EXISTS relationships (
    owner TEXT NOT NULL,
    about TEXT NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (owner, about)
);
"""

type Record = InteractionEvent | Memory | Flag | Relationship

FACT = "json_extract(data, '$.fact_id')"


def default_path() -> Path:
    """`$SIMILE_DB`, or `server/data/simile.db`."""
    return Path(os.environ.get("SIMILE_DB") or DEFAULT_PATH)


def recency(age: float, half_life: float) -> float:
    return 0.5 ** (max(age, 0.0) / half_life)


def seconds(half_life: timedelta) -> float:
    if half_life <= timedelta(0):
        raise ValueError(f"half_life must be positive, not {half_life}")
    return half_life.total_seconds()


def epoch(now: datetime) -> float:
    if now.tzinfo is None:
        raise ValueError(f"now must be timezone-aware, not {now!r}")
    return now.timestamp()


@dataclass(frozen=True)
class SharedHistory:
    """What two entities have been through together, oldest first."""

    events: list[InteractionEvent]
    flags: list[Flag]


class MemoryStore:
    """Events, flags, memories and relationships in one SQLite file. Thread-safe."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.create_function("recency", 2, recency, deterministic=True)
        self._db.executescript(SCHEMA)
        self._listeners: list[Callable[[Memory], None]] = []

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def listen(self, listener: Callable[[Memory], None]) -> Callable[[], None]:
        """Call `listener` with each memory once it's stored, and return a function that stops."""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def clear(self) -> None:
        """Forget every event, flag, memory and relationship. Other tables in the file stay."""
        with self._lock, self._db:
            for table in ("events", "flags", "memories", "relationships"):
                self._db.execute(f"DELETE FROM {table}")

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def add(self, *records: Record) -> None:
        """Store everything in one transaction. Events and memories are appended; a flag replaces
        any with its id, and a relationship replaces its pair's and stores its flags. Then each
        listener hears of each memory."""
        with self._lock, self._db:
            for record in records:
                match record:
                    case InteractionEvent():
                        self._insert(
                            "events",
                            actor=record.actor,
                            target=record.target,
                            time=record.timestamp.timestamp(),
                            magnitude=record.magnitude,
                            data=record.model_dump_json(),
                        )
                    case Memory():
                        self._insert(
                            "memories",
                            owner=record.owner,
                            kind=record.kind,
                            time=record.timestamp.timestamp(),
                            salience=record.salience,
                            data=record.model_dump_json(),
                        )
                    case Flag():
                        self._insert_flag(record)
                    case Relationship():
                        self._insert(
                            "relationships",
                            owner=record.owner,
                            about=record.about,
                            data=record.model_dump_json(exclude={"flags"}),
                        )
                        for flag in record.flags:
                            self._insert_flag(flag)
                    case _:
                        raise TypeError(f"can't store {type(record).__name__}")
        for memory in (record for record in records if isinstance(record, Memory)):
            for listener in list(self._listeners):
                try:
                    listener(memory)
                except Exception:
                    logger.exception("%r failed for %s's memory", listener, memory.owner)

    def _insert_flag(self, flag: Flag) -> None:
        self._insert(
            "flags",
            id=flag.id,
            owner=flag.owner,
            about=flag.about,
            created=flag.created.timestamp(),
            resolved=flag.resolved.timestamp() if flag.resolved else None,
            data=flag.model_dump_json(),
        )

    def _insert(self, table: str, **columns: object) -> None:
        names = ", ".join(columns)
        values = ", ".join(f":{name}" for name in columns)
        self._db.execute(f"INSERT OR REPLACE INTO {table} ({names}) VALUES ({values})", columns)

    def recall(
        self,
        owner: str,
        now: datetime,
        *,
        about: str | None = None,
        kind: MemoryKind | None = None,
        k: int = 5,
        half_life: timedelta = HALF_LIFE,
    ) -> list[Memory]:
        """`owner`'s top `k` memories by salience × recency, best first, without `facts`."""
        query = f"SELECT data FROM memories WHERE owner = :owner AND {FACT} IS NULL"
        if kind is not None:
            query += " AND kind = :kind"
        if about is not None:
            query += " AND :about IN (SELECT value FROM json_each(data, '$.about'))"
        query += (
            " ORDER BY salience * recency(:now - time, :half_life) DESC, time DESC, id DESC"
            " LIMIT :k"
        )
        rows = self._fetch(
            query,
            {
                "owner": owner,
                "kind": kind,
                "about": about,
                "now": epoch(now),
                "half_life": seconds(half_life),
                "k": k,
            },
        )
        return [Memory.model_validate_json(data) for (data,) in rows]

    def facts(self, owner: str) -> list[Memory]:
        """`owner`'s memories of the story's facts, oldest first."""
        rows = self._fetch(
            f"SELECT data FROM memories WHERE owner = :owner AND {FACT} IS NOT NULL"
            " ORDER BY time, id",
            {"owner": owner},
        )
        return [Memory.model_validate_json(data) for (data,) in rows]

    def forget_facts(self) -> int:
        """Forget everyone's memories of the story's facts, and return how many there were."""
        with self._lock, self._db:
            return self._db.execute(f"DELETE FROM memories WHERE {FACT} IS NOT NULL").rowcount

    def shared_history(
        self, a: str, b: str, now: datetime, *, k: int = 10, half_life: timedelta = HALF_LIFE
    ) -> SharedHistory:
        """The top `k` events between `a` and `b` by magnitude × recency, and the flags either
        holds about the other that are still open."""
        events = self._fetch(
            "SELECT data FROM ("
            " SELECT data, time, id FROM events"
            " WHERE (actor = :a AND target = :b) OR (actor = :b AND target = :a)"
            " ORDER BY magnitude * recency(:now - time, :half_life) DESC, time DESC, id DESC"
            " LIMIT :k"
            ") ORDER BY time, id",
            {"a": a, "b": b, "now": epoch(now), "half_life": seconds(half_life), "k": k},
        )
        flags = self._fetch(
            "SELECT data FROM flags"
            " WHERE ((owner = :a AND about = :b) OR (owner = :b AND about = :a))"
            " AND resolved IS NULL ORDER BY created, id",
            {"a": a, "b": b},
        )
        return SharedHistory(
            events=[InteractionEvent.model_validate_json(data) for (data,) in events],
            flags=[Flag.model_validate_json(data) for (data,) in flags],
        )

    def relationship(self, owner: str, about: str) -> Relationship | None:
        """How `owner` feels about `about`, with every flag `owner` holds about them."""
        with self._lock:
            row = self._db.execute(
                "SELECT data FROM relationships WHERE owner = ? AND about = ?", (owner, about)
            ).fetchone()
            return self._with_flags(row[0]) if row else None

    def relationships(self, owner: str) -> list[Relationship]:
        """How `owner` feels about everyone they know, by id."""
        with self._lock:
            rows = self._db.execute(
                "SELECT data FROM relationships WHERE owner = ? ORDER BY about", (owner,)
            ).fetchall()
            return [self._with_flags(data) for (data,) in rows]

    def _with_flags(self, data: str) -> Relationship:
        relationship = json.loads(data)
        flags = self._db.execute(
            "SELECT data FROM flags WHERE owner = ? AND about = ? ORDER BY created, id",
            (relationship["owner"], relationship["about"]),
        )
        relationship["flags"] = [json.loads(flag) for (flag,) in flags]
        return Relationship.model_validate(relationship)

    def _fetch(self, query: str, params: dict[str, Any]) -> list[tuple[str]]:
        with self._lock:
            return self._db.execute(query, params).fetchall()


def memory_of(app: Starlette) -> MemoryStore:
    """The server's store on `app.state.memory`, opened at `default_path()` on first use."""
    if not hasattr(app.state, "memory"):
        app.state.memory = MemoryStore(default_path())
    return app.state.memory
