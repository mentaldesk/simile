import json
import threading
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from PIL import Image

from simile.memory import MemoryStore
from simile.schema import CoreValue, Medium, Npc, Tile, Work
from simile.works import WorksStore
from simile.works.maker import MuralReply, Reply
from simile.works.painter import FakeImageModel
from simile.world.map import MuralWall

FIXTURES = Path(__file__).parents[1] / "fixtures"
NOW = datetime(2026, 3, 14, 12, tzinfo=UTC)


def npc(name: str) -> Npc:
    return Npc.model_validate_json((FIXTURES / "npcs" / f"{name}.json").read_text())


VIKTOR = npc("viktor")
SUKI = npc("suki")
MEI = npc("mei")
WALL = MuralWall("wall_1", 10, 5, 3, "south", 0.5, 1.5, Tile(x=11, y=7))
OTHER_WALL = MuralWall("wall_2", 20, 5, 2, "east", 0.0, 1.0, Tile(x=22, y=6))
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


def mural(id: str, artist: str = "suki", wall: str = "wall_1", hours_ago: float = 0) -> Work:
    return work(id, artist, hours_ago, medium=Medium.MURAL, wall=wall, form="bright murals")


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


def svg(width: int = 288, height: int = 262, inside: str = "") -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">'
        f'<rect width="{width}" height="{height}" fill="#e63946"/>'
        f'<circle cx="{width / 2}" cy="{height / 2}" r="{height / 3}" fill="#ffd166"/>'
        f"{inside}</svg>"
    )


def mural_reply(**fields: object) -> str:
    return MuralReply.model_validate(
        {
            "title": " Sunrise Over the Square ",
            "description": "A red wall with a yellow sun in the middle.",
            "statement": "Morning belongs to everyone.",
            "svg": svg(),
            "inspired_by": [1],
            "tags": ["Mornings", "the square"],
            "sentiment": 7.0,
            **{value.value: 0.0 for value in CoreValue},
            "freedom": 8.0,
            **fields,
        }
    ).model_dump_json()


class Hanging(FakeImageModel):
    """Hangs as a stuck GPU call would, until released. `painting` is set once it starts."""

    def __init__(self) -> None:
        super().__init__()
        self.painting = threading.Event()
        self.release = threading.Event()

    def paint(
        self, prompt: str, width: int, height: int, seed: int, step: Callable[[], None]
    ) -> Image.Image:
        self.painting.set()
        self.release.wait()
        return super().paint(prompt, width, height, seed, step)
