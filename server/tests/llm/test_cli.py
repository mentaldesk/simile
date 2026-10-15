import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from simile.cli import create_cli

MakeFakeCli = Callable[..., Any]

runner = CliRunner()


@pytest.fixture(autouse=True)
def temp_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))


def test_smoke_streams_a_reply_and_prints_timings(
    fake_cli: MakeFakeCli, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "set-by-test")
    cli = fake_cli(chunks=("Welcome", " in!"))

    result = runner.invoke(create_cli(), ["llm-smoke", "--cli-path", str(cli.path)])

    assert result.exit_code == 0, result.output
    assert "Dropping from the environment: ANTHROPIC_API_KEY" in result.output
    assert "Welcome in!" in result.output
    assert "latency" in result.output
    assert "first token" in result.output
    assert "API key source 'none'" in result.output
    assert "ANTHROPIC_API_KEY" not in cli.env
    assert (tmp_path / "simile-llm").is_dir()


def test_smoke_can_reuse_one_session(fake_cli: MakeFakeCli) -> None:
    cli = fake_cli()

    result = runner.invoke(
        create_cli(), ["llm-smoke", "--cli-path", str(cli.path), "--session", "--runs", "2"]
    )

    assert result.exit_code == 0, result.output
    assert "Session connected" in result.output
    assert result.output.count("latency") == 2
    assert len(cli.stdin) == 2
