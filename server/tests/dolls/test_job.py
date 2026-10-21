import json
import re
from contextlib import nullcontext
from pathlib import Path

import pytest
from pydantic import ValidationError

from simile.characters.palette import PLAYER
from simile.dolls import build, job
from simile.dolls.figure import FRAMES
from simile.dolls.flux import FakePainter
from simile.dolls.job import DOLL, Doll, main
from simile.jobs.report import PREFIX
from simile.schema import Appearance

from .keyed import keyed

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
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(job, "persona_of", lambda character: "A woman.")
    monkeypatch.setattr(build, "SIZE", (192, 256))
    work, out = tmp_path / "work", tmp_path / "out"
    work.mkdir()
    out.mkdir()
    (work / "params.json").write_text(json.dumps(params("new_face")))
    doll = Doll.model_validate(params("new_face"))
    painter = FakePainter()

    main(work, lambda: nullcontext(painter), keyed)
    result = DOLL.publish(doll, work, out)

    assert result == {
        "doll": "/api/jobs/files/doll/new_face.json",
        "painted": "/api/jobs/files/doll/new_face.webp",
    }
    published = sorted(path.name for path in out.iterdir())
    assert published == ["new_face.json", "new_face.webp"]
    assert all(re.fullmatch(DOLL.files, name) for name in published)
    manifest = json.loads((out / "new_face.json").read_text())
    assert manifest["painted"] == "new_face.webp"
    assert set(manifest["frames"]) == set(FRAMES)
    assert manifest["appearance"] == LOOK.model_dump(mode="json")
    assert "A woman." in painter.calls[0][0]
    reports = [line for line in capsys.readouterr().out.splitlines() if line.startswith(PREFIX)]
    assert len(reports) == len(FRAMES) + 2
    assert json.loads(reports[-1].removeprefix(PREFIX))["progress"] == 1.0


def test_says_what_it_needs_on_a_machine_without_flux(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from simile.dolls import flux

    (tmp_path / "params.json").write_text(json.dumps(params("new_face")))
    monkeypatch.setattr(flux, "find_spec", lambda name: None)

    with pytest.raises(SystemExit, match="uv sync --extra images"):
        main(tmp_path)


def test_a_character_the_library_doesnt_know_is_painted_as_a_person() -> None:
    assert job.persona_of("nobody_at_all") == ""


def test_needs_apple_silicon() -> None:
    assert DOLL.requires == ("apple_silicon",)
    assert DOLL.command(Doll.model_validate(params("player")), Path("w"))[1:] == [
        "-m",
        "simile.dolls.job",
        "w",
    ]
