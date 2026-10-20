import json
import re
from contextlib import nullcontext
from pathlib import Path

import pytest
from pydantic import ValidationError

from simile.characters.palette import PLAYER
from simile.dolls.job import DOLL, Doll, main
from simile.dolls.paint import FakeSheetPainter
from simile.jobs.report import PREFIX
from simile.schema import Appearance

LOOK = Appearance.model_validate(
    PLAYER.model_dump(mode="json") | {"hair_style": "bun", "accessories": ["scarf"]}
)


def params(character: str) -> dict:
    return {"character": character, "appearance": LOOK.model_dump(mode="json")}


@pytest.mark.parametrize("character", ["odalys", "desmond"])
def test_refuses_a_resident_whose_doll_is_in_content(character: str) -> None:
    with pytest.raises(ValidationError, match="in content"):
        Doll.model_validate(params(character))


def test_paints_a_new_character_and_publishes_what_the_client_loads(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    work, out = tmp_path / "work", tmp_path / "out"
    work.mkdir()
    out.mkdir()
    (work / "params.json").write_text(json.dumps(params("new_face")))
    doll = Doll.model_validate(params("new_face"))

    main(work, lambda: nullcontext(FakeSheetPainter()))
    result = DOLL.publish(doll, work, out)

    assert result == {
        "doll": "/api/jobs/files/doll/new_face.json",
        "flat": "/api/jobs/files/doll/new_face-flat.webp",
        "painted": "/api/jobs/files/doll/new_face-painted.webp",
    }
    published = sorted(path.name for path in out.iterdir())
    assert published == ["new_face-flat.webp", "new_face-painted.webp", "new_face.json"]
    assert all(re.fullmatch(DOLL.files, name) for name in published)
    manifest = json.loads((out / "new_face.json").read_text())
    assert (manifest["flat"], manifest["painted"]) == (
        "new_face-flat.webp",
        "new_face-painted.webp",
    )
    assert manifest["appearance"] == LOOK.model_dump(mode="json")
    reports = [line for line in capsys.readouterr().out.splitlines() if line.startswith(PREFIX)]
    assert len(reports) == 4
    assert json.loads(reports[-1].removeprefix(PREFIX))["progress"] == 1.0


def test_says_what_it_needs_on_a_machine_without_flux(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from simile.dolls import paint

    (tmp_path / "params.json").write_text(json.dumps(params("new_face")))
    monkeypatch.setattr(paint, "find_spec", lambda name: None)

    with pytest.raises(SystemExit, match="uv sync --extra images"):
        main(tmp_path)


def test_needs_apple_silicon() -> None:
    assert DOLL.requires == ("apple_silicon",)
    assert DOLL.command(Doll.model_validate(params("player")), Path("w"))[1:] == [
        "-m",
        "simile.dolls.job",
        "w",
    ]
