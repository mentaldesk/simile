from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from simile.creatures import build, preview
from simile.creatures.cli import register
from simile.dolls import flux


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

    result = CliRunner().invoke(app, ["creatures", "paint", "rat"])

    assert result.exit_code == 1
    assert "uv sync --extra images" in result.output
    assert "Traceback" not in result.output


def test_refuses_a_creature_that_isnt_there(app: typer.Typer) -> None:
    result = CliRunner().invoke(app, ["creatures", "paint", "dragon"])

    assert result.exit_code == 1
    assert "No creature called dragon" in result.output


def test_draws_the_preview_again(app: typer.Typer, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(preview, "write_preview", lambda: Path("preview.webp"))

    result = CliRunner().invoke(app, ["creatures", "preview"])

    assert result.exit_code == 0
    assert result.output == "wrote preview.webp\n"
