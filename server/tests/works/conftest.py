import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from simile.memory import MemoryStore
from simile.schema import CoreValue, Medium, Npc, Work
from simile.works import WorksStore
from simile.works.maker import Reply

FIXTURES = Path(__file__).parents[1] / "fixtures"
NOW = datetime(2026, 3, 14, 12, tzinfo=UTC)


def npc(name: str) -> Npc:
    return Npc.model_validate_json((FIXTURES / "npcs" / f"{name}.json").read_text())


VIKTOR = npc("viktor")
SUKI = npc("suki")
MEI = npc("mei")
FIXTURE_WORKS = [
    Work.model_validate(work) for work in json.loads((FIXTURES / "works.json").read_text())
]


def work(id: str, artist: str = "viktor", hours_ago: float = 0, **fields: object) -> Work:
    mural = fields.get("medium") is Medium.MURAL
    return Work.model_validate(
        {
            "id": id,
            "artist": artist,
            "medium": Medium.WRITING,
            "form": "plain verse about old bridges",
            "title": f"Piece {id}",
            "created": NOW - timedelta(hours=hours_ago),
            "text": "A line.",
            "statement": f"What {id} says.",
            "inspired_by": [],
            "values": {value: 0.0 for value in CoreValue},
            "tags": [],
            "sentiment": 0.0,
            "wall": "wall_1" if mural else None,
            **fields,
        }
    )


def reply(**fields: object) -> str:
    return Reply.model_validate(
        {
            "title": " The Footbridge ",
            "text": "They built it for a hundred years.\nThe arch has held for ninety-one.",
            "statement": "Things last when people look after them.",
            "inspired_by": [2, 1, 9, 2, 0],
            "tags": [" Repair ", "The old footbridge", "boredom", "bridges"],
            "sentiment": 3.0,
            **{value.value: 0.0 for value in CoreValue},
            "tradition": 8.0,
            "responsibility": 7.5,
            **fields,
        }
    ).model_dump_json()


@pytest.fixture
def works() -> Iterator[WorksStore]:
    with WorksStore(":memory:") as store:
        yield store


@pytest.fixture
def memory() -> Iterator[MemoryStore]:
    with MemoryStore(":memory:") as store:
        yield store
