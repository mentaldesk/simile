from pathlib import Path

import pytest
from typer.testing import CliRunner

from simile.cli import create_cli
from simile.protocol import export


def test_committed_json_schema_is_up_to_date() -> None:
    assert not export.outdated(), "Run `uv run simile protocol` in server/ and commit the result."


def test_outdated_when_missing_or_changed(tmp_path: Path) -> None:
    path = tmp_path / "protocol.schema.json"
    assert export.outdated(path)

    export.write(path)
    assert not export.outdated(path)

    path.write_text("{}")
    assert export.outdated(path)


def test_cli_writes_the_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    monkeypatch.setattr(export, "write", lambda: calls.append("write"))

    result = CliRunner().invoke(create_cli(), ["protocol"])

    assert result.exit_code == 0, result.output
    assert calls == ["write"]
