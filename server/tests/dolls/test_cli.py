from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from simile.dolls import build, flux
from simile.dolls.cli import register


@pytest.fixture
def app() -> typer.Typer:
    cli = typer.Typer()
    register(cli)
    return cli


def loads(painter, **kwargs) -> list:
    """`build`, as far as loading the painter."""
    painter()
    return []


def test_says_what_painting_needs_without_a_traceback(
    app: typer.Typer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(flux, "find_spec", lambda name: None)
    monkeypatch.setattr(build, "build", loads)

    result = CliRunner().invoke(app, ["dolls", "paint", "player"])

    assert result.exit_code == 1
    assert "Painting dolls needs FLUX" in result.output
    assert "uv sync --extra images" in result.output
    assert "Traceback" not in result.output


def test_a_failure_while_painting_keeps_its_traceback(
    app: typer.Typer, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fails(painter, **kwargs) -> list:
        raise RuntimeError("Metal ran out of memory")

    monkeypatch.setattr(build, "build", fails)

    result = CliRunner().invoke(app, ["dolls", "paint", "player"])

    assert isinstance(result.exception, RuntimeError)
    assert "Metal ran out of memory" not in result.output


def test_refuses_someone_who_isnt_there(app: typer.Typer) -> None:
    result = CliRunner().invoke(app, ["dolls", "paint", "nobody"])

    assert result.exit_code == 1
    assert "No resident or player called nobody" in result.output


def test_measures_the_seats_again_and_names_what_it_wrote(
    app: typer.Typer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(build, "reseat", lambda: [Path("desmond.json")])

    result = CliRunner().invoke(app, ["dolls", "seats"])

    assert result.exit_code == 0
    assert result.output == "wrote desmond.json\n"
