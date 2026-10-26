import pytest
import typer
from typer.testing import CliRunner

from simile.dolls import flux
from simile.icons import build
from simile.icons.cli import register


@pytest.fixture
def app() -> typer.Typer:
    cli = typer.Typer()
    register(cli)
    return cli


def test_says_what_painting_needs_without_a_traceback(
    app: typer.Typer, monkeypatch: pytest.MonkeyPatch
) -> None:
    def loads(painter, **kwargs) -> list:
        painter()
        return []

    monkeypatch.setattr(flux, "find_spec", lambda name: None)
    monkeypatch.setattr(build, "build", loads)

    result = CliRunner().invoke(app, ["icons", "paint", "eye"])

    assert result.exit_code == 1
    assert "uv sync --extra images" in result.output
    assert "Traceback" not in result.output


def test_refuses_an_icon_that_isnt_there(app: typer.Typer) -> None:
    result = CliRunner().invoke(app, ["icons", "paint", "crown"])

    assert result.exit_code == 1
    assert "No icon called crown" in result.output
