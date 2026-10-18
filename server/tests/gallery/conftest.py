from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from simile.gallery import GalleryStore
from simile.memory import MemoryStore
from simile.npc import load_npcs
from simile.schema import CoreValue, Craft, Medium, Npc, Work
from simile.works import WorksStore
from simile.works.maker import PaintingReply
from simile.world.map import load_maps

NOW = datetime(2026, 3, 14, 12, tzinfo=UTC)
MAPS = load_maps()
RESIDENTS = {npc.id: npc for npc in load_npcs()}
KOFI = RESIDENTS["kofi"]
TOBIAS = RESIDENTS["tobias"]


def painting(id: str, artist: str = "kofi", hours_ago: float = 0, **fields: object) -> Work:
    return Work.model_validate(
        {
            "id": id,
            "artist": artist,
            "medium": Medium.PAINTING,
            "form": "political street murals",
            "title": f"Painting {id}",
            "created": NOW - timedelta(hours=hours_ago),
            "text": "Blue squares on a red field.",
            "statement": f"What {id} says.",
            "inspired_by": [],
            "values": {value: 0.0 for value in CoreValue},
            "tags": ["squares", "red"],
            "sentiment": 0.0,
            **fields,
        }
    )


def painter(npc: Npc, form: str = "small oil studies of the harbour") -> Npc:
    return npc.model_copy(update={"craft": Craft(medium=Medium.PAINTING, form=form)})


@pytest.fixture
def works() -> Iterator[WorksStore]:
    with WorksStore(":memory:") as store:
        yield store


@pytest.fixture
def memory() -> Iterator[MemoryStore]:
    with MemoryStore(":memory:") as store:
        yield store


@pytest.fixture
def store() -> Iterator[GalleryStore]:
    with GalleryStore(":memory:") as gallery:
        yield gallery


@pytest.fixture
def database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "simile.db"
    monkeypatch.setenv("SIMILE_DB", str(path))
    return path


def svg(width: int = 960, height: int = 602) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">'
        f'<rect width="{width}" height="{height}" fill="#1d3557"/>'
        f'<rect x="{width / 4}" y="{height / 4}" width="{width / 2}" height="{height / 2}" '
        'fill="#f1c40f"/></svg>'
    )


def painting_reply(**fields: object) -> str:
    return PaintingReply.model_validate(
        {
            "title": "Harbour at Dusk",
            "description": "A yellow square on deep blue.",
            "statement": "Every boat comes home eventually.",
            "svg": svg(),
            "inspired_by": [],
            "tags": ["harbour", "dusk"],
            "sentiment": 6.0,
            **{value.value: 0.0 for value in CoreValue},
            "peace_of_mind": 7.0,
            **fields,
        }
    ).model_dump_json()
