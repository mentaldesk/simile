from pathlib import Path

import pytest
from PIL import Image
from typer.testing import CliRunner

from simile.cli import create_cli
from simile.gallery import GalleryStore
from simile.llm import FakeProvider
from simile.memory import MemoryStore
from simile.persistence import SavedWorld, WorldStore
from simile.schema import Medium
from simile.works import WorksStore
from simile.works.render import painting_canvas

from .conftest import KOFI, NOW, painting_reply

runner = CliRunner()


def test_paints_a_canvas_and_hangs_it(
    database: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with MemoryStore(database) as memory, WorldStore(memory) as world:
        world.save(SavedWorld(now=NOW, npcs={}))
    monkeypatch.setattr(
        "simile.llm.lifespan.CannedProvider", lambda: FakeProvider([painting_reply()])
    )
    out = tmp_path / "harbour.png"

    result = runner.invoke(create_cli(), ["gallery", "paint", "kofi", "--png", str(out)])

    assert result.exit_code == 0, result.output
    with WorksStore(database) as works, GalleryStore(database) as store:
        [made] = works.by("kofi")
        hanging = store.hanging()
    assert (made.medium, made.created) == (Medium.PAINTING, NOW)
    assert list(hanging.values()) == [made.id]
    assert f'"Harbour at Dusk", {KOFI.craft.form if KOFI.craft else ""}, by {KOFI.name}' in (
        result.output
    )
    assert result.output.endswith(f"Hung in {next(iter(hanging))[1]} on gallery.\n")
    assert Image.open(out).size == painting_canvas()


@pytest.mark.usefixtures("database")
def test_only_painters_and_muralists_paint() -> None:
    result = runner.invoke(create_cli(), ["gallery", "paint", "tobias"])

    assert result.exit_code == 1
    assert "doesn't paint" in result.output
