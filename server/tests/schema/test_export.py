import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from typer.testing import CliRunner

from simile.cli import create_cli
from simile.schema import MODELS, export

FIXTURES = Path(__file__).parents[1] / "fixtures"

runner = CliRunner()


def schema(name: str) -> Draft202012Validator:
    return Draft202012Validator(json.loads((export.JSON_DIR / f"{name}.json").read_text()))


def test_committed_json_schema_is_up_to_date() -> None:
    assert export.outdated() == [], "Run `uv run simile schema` in server/ and commit the result."


def test_write_creates_every_model_and_removes_stale_files(tmp_path: Path) -> None:
    (tmp_path / "Removed.json").write_text("{}")

    export.write(tmp_path)

    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(
        f"{m.__name__}.json" for m in MODELS
    )
    assert export.outdated(tmp_path) == []


def test_outdated_lists_changed_missing_and_extra_files(tmp_path: Path) -> None:
    export.write(tmp_path)
    (tmp_path / "Npc.json").write_text("{}")
    (tmp_path / "Line.json").unlink()
    (tmp_path / "Extra.json").write_text("{}")

    assert export.outdated(tmp_path) == ["Extra.json", "Line.json", "Npc.json"]


def test_cli_check_passes_when_up_to_date() -> None:
    result = runner.invoke(create_cli(), ["schema", "--check"])

    assert result.exit_code == 0, result.output


def test_cli_check_fails_when_out_of_date(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(export, "outdated", lambda: ["Npc.json"])

    result = runner.invoke(create_cli(), ["schema", "--check"])

    assert result.exit_code == 1
    assert "Npc.json" in result.output


@pytest.mark.parametrize(
    ("name", "fixture"),
    [
        ("Npc", "npcs/mei.json"),
        ("Location", "locations.json"),
        ("Relationship", "relationships.json"),
        ("InteractionEvent", "interaction_events.json"),
        ("Memory", "memories.json"),
        ("NewsItem", "news_items.json"),
        ("Conversation", "conversations.json"),
    ],
)
def test_exported_schema_accepts_fixtures(name: str, fixture: str) -> None:
    data = json.loads((FIXTURES / fixture).read_text())

    for item in data if isinstance(data, list) else [data]:
        schema(name).validate(item)


def test_exported_schema_rejects_unknown_fields() -> None:
    assert not schema("NewsItem").is_valid(
        {"id": "x", "title": "t", "url": "u", "summary": "s", "published": "2026-01-01T00:00:00Z"}
        | {"author": "a"}
    )
