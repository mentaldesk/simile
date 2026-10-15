import threading
from datetime import UTC, datetime
from itertools import permutations
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter

import simile.memory.store as store_module
from simile.memory import MemoryStore, default_path
from simile.schema import InteractionEvent, Memory, MemoryKind, Model, Relationship

FIXTURES = Path(__file__).parents[1] / "fixtures"
NOW = datetime(2026, 3, 14, 12, tzinfo=UTC)
ENTITIES = ("mei", "viktor", "suki", "player")


def load[T: Model](name: str, model: type[T]) -> list[T]:
    return TypeAdapter(list[model]).validate_json((FIXTURES / name).read_bytes())


def everything(store: MemoryStore) -> dict[str, Any]:
    return {
        "memories": {who: store.recall(who, NOW, k=100) for who in ENTITIES},
        "history": {
            (a, b): store.shared_history(a, b, NOW, k=100) for a, b in permutations(ENTITIES, 2)
        },
        "relationships": {who: store.relationships(who) for who in ENTITIES},
    }


def test_everything_survives_reopening_the_database(tmp_path: Path) -> None:
    memories = load("memories.json", Memory)
    events = load("interaction_events.json", InteractionEvent)
    relationships = load("relationships.json", Relationship)
    path = tmp_path / "village" / "simile.db"

    with MemoryStore(path) as first:
        first.add(*memories, *events, *relationships)
        before = everything(first)

    with MemoryStore(path) as reopened:
        assert everything(reopened) == before

    assert sum(len(found) for found in before["memories"].values()) == len(memories)
    assert sum(len(h.events) for h in before["history"].values()) == 2 * len(events)
    assert sum(len(found) for found in before["relationships"].values()) == len(relationships)
    assert before["relationships"]["mei"][1] == relationships[0]


def test_store_can_be_shared_across_threads(store: MemoryStore) -> None:
    remembered = Memory(
        owner="mei", kind=MemoryKind.OBSERVATION, content="hi", salience=1, valence=0, timestamp=NOW
    )
    writer = threading.Thread(target=store.add, args=(remembered,))
    writer.start()
    writer.join()

    assert store.recall("mei", NOW) == [remembered]


def test_default_path_comes_from_simile_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SIMILE_DB", str(tmp_path / "custom.db"))

    assert default_path() == tmp_path / "custom.db"


def test_default_path_is_in_a_folder_git_ignores(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("SIMILE_DB", raising=False)
    monkeypatch.setattr(store_module, "DATA", tmp_path / "data")

    assert default_path() == tmp_path / "data" / "simile.db"
    assert (tmp_path / "data" / ".gitignore").read_text() == "*\n"
