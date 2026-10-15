from collections.abc import Callable, Iterator, Sequence
from datetime import UTC, datetime, timedelta

import pytest

from simile.memory import MemoryStore
from simile.npc import load_npcs
from simile.schema import Conversation, CoreValue, Line, Npc

START = datetime(2026, 1, 1, 9, tzinfo=UTC)

type Talk = Callable[..., Conversation]


def make_npc(id: str, name: str, **values: float) -> Npc:
    """An NPC who cares about everything at 0.5, except the values given."""
    scores = {value: values.get(value.value, 0.5) for value in CoreValue}
    return load_npcs()[0].model_copy(update={"id": id, "name": name, "values": scores})


@pytest.fixture
def npcs() -> dict[str, Npc]:
    ana = make_npc("ana", "Ana Ferreira", compassion=0.9, honesty=0.8, ambition=0.1)
    ben = make_npc("ben", "Ben Okafor", tradition=0.9, obedience=0.8, creativity=0.2)
    return {ana.id: ana, ben.id: ben}


@pytest.fixture
def store() -> Iterator[MemoryStore]:
    with MemoryStore(":memory:") as store:
        yield store


@pytest.fixture
def talk() -> Talk:
    """A finished conversation with these (speaker, text) lines, two minutes long."""

    def make(
        *lines: tuple[str, str],
        participants: Sequence[str] = ("ana", "ben"),
        id: str = "talk_1",
        started: datetime = START,
    ) -> Conversation:
        return Conversation(
            id=id,
            participants=list(participants),
            started=started,
            ended=started + timedelta(minutes=2),
            lines=[
                Line(
                    id=n,
                    conversation_id=id,
                    speaker=speaker,
                    text=text,
                    timestamp=started + timedelta(seconds=10 * n),
                    duration=3,
                )
                for n, (speaker, text) in enumerate(lines, start=1)
            ],
        )

    return make
