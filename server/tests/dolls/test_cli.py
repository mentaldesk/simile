import pytest
import typer
from typer.testing import CliRunner

from simile.dolls import build, paint
from simile.dolls.cli import register


@pytest.fixture
def app() -> typer.Typer:
    cli = typer.Typer()
    register(cli)
    return cli


def test_says_what_painting_needs_without_a_traceback(
    app: typer.Typer, monkeypatch: pytest.MonkeyPatch
) -> None:
    def missing() -> None:
        raise RuntimeError("Painting dolls needs part 3's painter, simile.papercraft")

    def loads_the_painter(painter, **kwargs) -> list:
        painter()
        return []

    monkeypatch.setattr(paint, "EditPainter", missing)
    monkeypatch.setattr(build, "build", loads_the_painter)

    result = CliRunner().invoke(app, ["dolls", "paint", "player"])

    assert result.exit_code == 1
    assert "needs part 3's painter" in result.output
    assert "Traceback" not in result.output


def test_refuses_someone_who_isnt_there(app: typer.Typer) -> None:
    result = CliRunner().invoke(app, ["dolls", "paint", "nobody"])

    assert result.exit_code == 1
    assert "No resident or player called nobody" in result.output
