from datetime import timedelta

from simile.memory import MemoryStore
from simile.schema import Memory, MemoryKind

from .test_store import NOW, memory


def of_fact(content: str, fact_id: str, *, owner: str = "mei", days_ago: float = 8) -> Memory:
    return Memory(
        owner=owner,
        kind=MemoryKind.OBSERVATION,
        content=content,
        salience=1.0,
        valence=-0.5,
        timestamp=NOW - timedelta(days=days_ago),
        about=["aris", "kofi"],
        fact_id=fact_id,
    )


def test_recall_leaves_out_memories_of_the_incident(store: MemoryStore) -> None:
    store.add(
        of_fact("I heard shouting at the maker space.", "shouting", days_ago=0),
        memory("Kofi showed me his mural.", about=("kofi",), salience=0.1),
    )

    assert [m.content for m in store.recall("mei", NOW)] == ["Kofi showed me his mural."]
    assert [m.content for m in store.recall("mei", NOW, about="kofi")] == [
        "Kofi showed me his mural."
    ]
    assert store.recall("mei", NOW, kind=MemoryKind.OBSERVATION) == []


def test_facts_are_an_owners_memories_of_the_incident_oldest_first(store: MemoryStore) -> None:
    seen = of_fact("I saw someone in a red top.", "seen", days_ago=8)
    gone = of_fact("Her workshop was found open.", "gone", days_ago=1)
    store.add(
        gone,
        memory("Kofi showed me his mural."),
        seen,
        of_fact("I was there.", "there_kofi", owner="kofi"),
    )

    assert store.facts("mei") == [seen, gone]
    assert store.facts("ben") == []
