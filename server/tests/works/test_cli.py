from pathlib import Path

import pytest
from PIL import Image
from typer.testing import CliRunner

from simile.cli import create_cli
from simile.llm import FakeProvider
from simile.memory import MemoryStore
from simile.npc import load_npcs
from simile.persistence import SavedWorld, WorldStore
from simile.schema import Memory, MemoryKind
from simile.works import WorksStore

from .conftest import NOW, mural_reply, reply, svg

runner = CliRunner()

RIVER = Memory(
    owner="tobias",
    kind=MemoryKind.NEWS,
    content='I read "Dredging the river to start in spring" on the news terminal. About time.',
    salience=0.8,
    valence=0.6,
    timestamp=NOW,
    news_id="news-1",
)


@pytest.fixture
def database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "simile.db"
    monkeypatch.setenv("SIMILE_DB", str(path))
    return path


def test_writes_a_piece_at_the_saved_time_and_stores_it(
    database: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with MemoryStore(database) as memory, WorldStore(memory) as world:
        memory.add(RIVER)
        world.save(SavedWorld(now=NOW, npcs={}))
    monkeypatch.setattr(
        "simile.llm.lifespan.CannedProvider", lambda: FakeProvider([reply(inspired_by=[1])])
    )

    result = runner.invoke(create_cli(), ["works", "make", "tobias"])

    assert result.exit_code == 0, result.output
    with WorksStore(database) as works:
        [made] = works.by("tobias")
    assert made.created == NOW
    assert made.inspired_by == ["news-1"]
    assert result.output.startswith(
        f"On their mind (* inspired it; valence, salience):\n* +0.6 0.8  {RIVER.content}\n\n"
    )
    assert '"The Footbridge", plain verse about the river, by Tobias Fallon\n\n' in result.output
    assert "Statement: Things last when people look after them.\n" in result.output
    assert "Values: tradition 0.8, responsibility 0.8, " in result.output
    assert result.output.endswith(f"Stored as {made.id}.\n")
    with MemoryStore(database) as memory:
        assert [m.work_id for m in memory.recall("tobias", NOW, kind=MemoryKind.WORK)] == [made.id]


def test_says_when_the_model_couldnt_write_a_piece(database: Path) -> None:
    result = runner.invoke(create_cli(), ["works", "make", "tobias"])

    assert result.exit_code == 1
    assert "Tobias Fallon couldn't write a piece." in result.output
    with WorksStore(database) as works:
        assert works.by("tobias") == []


def test_paints_a_mural_on_the_wall_they_pick_and_saves_its_picture(
    database: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "simile.llm.lifespan.CannedProvider",
        lambda: FakeProvider([mural_reply(svg=svg(384, 563))]),
    )

    result = runner.invoke(
        create_cli(), ["works", "make", "kofi", "--png", str(tmp_path / "mural.png")]
    )

    assert result.exit_code == 0, result.output
    with WorksStore(database) as works:
        [made] = works.by("kofi")
        assert works.showing() == {"corner_shop": made}
    assert Image.open(tmp_path / "mural.png").size == (384, 563)
    assert (
        '"Sunrise Over the Square", political street murals, by Kofi Lindqvist-Mensah on the '
        "corner shop wall\n\nA red wall with a yellow sun in the middle.\n\n"
    ) in result.output
    assert result.output.endswith(f"Stored as {made.id}.\n")


def test_paints_the_wall_its_told_to(database: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "simile.llm.lifespan.CannedProvider",
        lambda: FakeProvider([mural_reply(svg=svg(288, 223))]),
    )

    result = runner.invoke(create_cli(), ["works", "make", "odalys", "--wall", "daily_grind"])
    nowhere = runner.invoke(create_cli(), ["works", "make", "odalys", "--wall", "nowhere"])

    assert result.exit_code == 0, result.output
    with WorksStore(database) as works:
        assert [m.wall for m in works.by("odalys")] == ["daily_grind"]
    assert nowhere.exit_code == 2
    assert "no such wall: nowhere" in nowhere.output


def test_says_when_a_muralist_couldnt_paint(database: Path) -> None:
    result = runner.invoke(create_cli(), ["works", "make", "kofi"])

    assert result.exit_code == 1
    assert "Kofi Lindqvist-Mensah couldn't paint a mural." in result.output


def test_only_residents_with_a_craft_can_make_something(
    database: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    [kofi] = [npc for npc in load_npcs() if npc.id == "kofi"]
    monkeypatch.setattr("simile.npc.load_npcs", lambda: [kofi.model_copy(update={"craft": None})])

    idle = runner.invoke(create_cli(), ["works", "make", "kofi"])
    nobody = runner.invoke(create_cli(), ["works", "make", "nobody"])

    assert idle.exit_code == 1
    assert "Kofi Lindqvist-Mensah doesn't make anything." in idle.output
    assert nobody.exit_code == 2
    assert "no such resident: nobody" in nobody.output
