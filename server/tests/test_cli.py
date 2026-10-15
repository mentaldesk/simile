from pathlib import Path

import pytest
from typer.testing import CliRunner

from simile.cli import create_cli

runner = CliRunner()


@pytest.fixture
def fake_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    root = tmp_path / "fakesim"
    (root / "alpha").mkdir(parents=True)
    (root / "beta").mkdir()
    (root / "__init__.py").write_text("")
    (root / "alpha" / "__init__.py").write_text("")
    (root / "alpha" / "cli.py").write_text(
        "import typer\n"
        "def register(app: typer.Typer) -> None:\n"
        "    @app.command()\n"
        "    def hello() -> None:\n"
        "        print('hello from alpha')\n"
    )
    (root / "beta" / "__init__.py").write_text("")
    monkeypatch.syspath_prepend(tmp_path)
    return "fakesim"


def test_help_lists_serve() -> None:
    result = runner.invoke(create_cli(), ["--help"])

    assert result.exit_code == 0
    assert "serve" in result.output


def test_registers_commands_from_module_cli(fake_package: str) -> None:
    result = runner.invoke(create_cli(fake_package), ["hello"])

    assert result.exit_code == 0, result.output
    assert "hello from alpha" in result.output
