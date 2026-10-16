import dataclasses
import json
import sqlite3
import time
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta
from pathlib import Path
from types import TracebackType
from typing import Self

from simile.behaviour import Behaviour
from simile.llm import CallRecord, LLMClient
from simile.memory import MemoryStore
from simile.schema import Conversation, LocationKind, Relationship
from simile.sim import ConversationEnded, World
from simile.social import as_of, meet

HOME = "home"
STREET = "street"
TERMINAL = "terminal"

SCHEMA = """
CREATE TABLE IF NOT EXISTS record_runs (
    id INTEGER PRIMARY KEY,
    started REAL NOT NULL,
    ended REAL,
    wall_started REAL NOT NULL,
    wall_ended REAL,
    speed REAL NOT NULL,
    npcs TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS record_samples (
    run INTEGER NOT NULL,
    time REAL NOT NULL,
    npc TEXT NOT NULL,
    place TEXT NOT NULL,
    location TEXT,
    activity TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS record_samples_by_run ON record_samples (run);

CREATE TABLE IF NOT EXISTS record_conversations (
    run INTEGER NOT NULL,
    id TEXT NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (run, id)
);

CREATE TABLE IF NOT EXISTS record_llm_calls (
    run INTEGER NOT NULL,
    time REAL NOT NULL,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS record_llm_calls_by_run ON record_llm_calls (run);

CREATE TABLE IF NOT EXISTS record_relationships (
    run INTEGER NOT NULL,
    phase TEXT NOT NULL,
    owner TEXT NOT NULL,
    about TEXT NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (run, phase, owner, about)
);
"""

type Sample = tuple[datetime, str, str, str | None, str]
"""Time, NPC, place, location id and activity."""


class RecordStore:
    """Recorded runs, in their own `record_*` tables of R2's database file."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._db = sqlite3.connect(path)
        self._db.executescript(SCHEMA)

    def close(self) -> None:
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

    def begin(self, started: datetime, speed: float, npcs: Iterable[str]) -> int:
        with self._db:
            cursor = self._db.execute(
                "INSERT INTO record_runs (started, wall_started, speed, npcs) VALUES (?, ?, ?, ?)",
                (started.timestamp(), time.time(), speed, json.dumps(sorted(npcs))),
            )
        assert cursor.lastrowid is not None
        return cursor.lastrowid

    def end(self, run: int, ended: datetime) -> None:
        with self._db:
            self._db.execute(
                "UPDATE record_runs SET ended = ?, wall_ended = ? WHERE id = ?",
                (ended.timestamp(), time.time(), run),
            )

    def add(
        self,
        run: int,
        *,
        samples: Iterable[Sample] = (),
        conversations: Iterable[Conversation] = (),
        calls: Iterable[tuple[datetime, CallRecord]] = (),
        relationships: tuple[str, Iterable[Relationship]] | None = None,
    ) -> None:
        with self._db:
            self._db.executemany(
                "INSERT INTO record_samples (run, time, npc, place, location, activity)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                [(run, when.timestamp(), *rest) for when, *rest in samples],
            )
            self._db.executemany(
                "INSERT OR REPLACE INTO record_conversations (run, id, data) VALUES (?, ?, ?)",
                [(run, c.id, c.model_dump_json()) for c in conversations],
            )
            self._db.executemany(
                "INSERT INTO record_llm_calls (run, time, data) VALUES (?, ?, ?)",
                [
                    (run, when.timestamp(), json.dumps(dataclasses.asdict(record)))
                    for when, record in calls
                ],
            )
            if relationships is not None:
                phase, found = relationships
                self._db.executemany(
                    "INSERT OR REPLACE INTO record_relationships"
                    " (run, phase, owner, about, data) VALUES (?, ?, ?, ?, ?)",
                    [
                        (run, phase, r.owner, r.about, r.model_dump_json(exclude={"flags"}))
                        for r in found
                    ],
                )


class Recorder:
    """Records a run for `simile report`: where each NPC is every sim minute, every finished
    conversation, every LLM call, and every NPC's relationships at the start and the end.
    Rows are buffered and written once a sim minute, so the tick never waits on more than one
    small transaction."""

    def __init__(
        self,
        store: RecordStore,
        world: World,
        behaviour: Behaviour,
        memory: MemoryStore,
        llm: LLMClient | None,
        *,
        every: timedelta = timedelta(minutes=1),
    ) -> None:
        self.store = store
        self.world = world
        self.behaviour = behaviour
        self.memory = memory
        self.llm = llm
        self.every = every
        self.run: int | None = None
        self._next = world.clock.now
        self._samples: list[Sample] = []
        self._conversations: list[Conversation] = []
        self._calls: list[tuple[datetime, CallRecord]] = []
        self._stops: list[Callable[[], None]] = []

    def start(self) -> int:
        clock = self.world.clock
        self.run = run = self.store.begin(clock.now, clock.speed, self.behaviour.npcs)
        self.store.add(run, relationships=("start", self.relationships(clock.now)))
        self._next = clock.now
        self._stops = [
            self.world.loop.register(self),
            self.world.bus.subscribe(ConversationEnded, self.on_ended),
        ]
        if (llm := self.llm) is not None:
            llm.listeners.append(self.on_call)
            self._stops.append(lambda: llm.listeners.remove(self.on_call))
        return run

    def finish(self) -> None:
        if self.run is None:
            return
        for stop in reversed(self._stops):
            stop()
        self._stops = []
        now = self.world.clock.now
        self._flush()
        self.store.add(self.run, relationships=("end", self.relationships(now)))
        self.store.end(self.run, now)

    def tick(self, dt: float) -> None:
        now = self.world.clock.now
        if now < self._next:
            return
        self._next += self.every
        for npc in self.behaviour.npcs.values():
            place, location = self.place(npc.id, npc.home)
            activity = self.behaviour.goal(npc.id).activity.value
            self._samples.append((now, npc.id, place, location, activity))
        self._flush()

    def on_ended(self, event: ConversationEnded) -> None:
        self._conversations.append(event.conversation)

    def on_call(self, record: CallRecord) -> None:
        self._calls.append((self.world.clock.now, record))

    def place(self, npc: str, home: str) -> tuple[str, str | None]:
        """Where `npc` is, as B1's fast-forward counts it, and the location id."""
        location = self.behaviour.places.at(self.behaviour.movement.position(npc))
        if location is None:
            return STREET, None
        if location.kind is LocationKind.HOUSE:
            return (HOME if location.id == home else STREET), location.id
        if location.kind is LocationKind.TERMINAL:
            return TERMINAL, location.id
        return location.id, location.id

    def relationships(self, now: datetime) -> list[Relationship]:
        """How every NPC feels about everyone they know, and strangers they'd `meet`, at `now`."""
        found = []
        for owner in self.behaviour.npcs.values():
            known = {rel.about: rel for rel in self.memory.relationships(owner.id)}
            for other in self.behaviour.npcs:
                if other != owner.id and other not in known:
                    known[other] = meet(owner, other)
            found += [as_of(rel, now) for rel in known.values()]
        return found

    def _flush(self) -> None:
        assert self.run is not None
        self.store.add(
            self.run,
            samples=self._samples,
            conversations=self._conversations,
            calls=self._calls,
        )
        self._samples, self._conversations, self._calls = [], [], []
