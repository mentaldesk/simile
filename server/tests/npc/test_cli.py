from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from simile.cli import create_cli
from simile.llm import FakeProvider, LLMClient
from simile.npc.content import NPCS_DIR, load_npcs
from simile.npc.generate import plan

runner = CliRunner()


def test_generate_npcs_writes_the_village(
    residents: Callable[[], FakeProvider], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = residents()
    monkeypatch.setattr(LLMClient, "provider", property(lambda client: fake))

    result = runner.invoke(
        create_cli(), ["generate-npcs", "--count", "3", "--seed", "2", "--out", str(tmp_path)]
    )

    assert result.exit_code == 0, result.output
    npcs = load_npcs(tmp_path)
    assert sorted(npc.home for npc in npcs) == ["house_1", "house_2", "house_3"]
    assert "--seed 2" in (tmp_path / "README.md").read_text()
    assert "house_1: Ana Folau (ana), " in result.output
    assert "with 3 Claude calls" in result.output


@pytest.mark.parametrize("count", ["0", "11"])
def test_generate_npcs_needs_a_home_for_everyone(count: str, tmp_path: Path) -> None:
    args = ["generate-npcs", "--count", count, "--out", str(tmp_path)]

    result = runner.invoke(create_cli(), args)

    assert result.exit_code != 0
    assert "one per home" in result.output
    assert not list(tmp_path.iterdir())


def test_a_rich_brief_writes_the_sampled_residents_to_out(
    residents: Callable[[], FakeProvider], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = residents()
    monkeypatch.setattr(LLMClient, "provider", property(lambda client: fake))
    args = ["generate-npcs", "--count", "3", "--seed", "2", "--rich-brief", "--out", str(tmp_path)]

    result = runner.invoke(create_cli(), args)

    assert result.exit_code == 0, result.output
    facts = [brief.facts for brief in plan(3, 2, rich=True) if brief.facts]
    assert sorted(npc.name for npc in load_npcs(tmp_path)) == sorted(f.name for f in facts)
    readme = (tmp_path / "README.md").read_text()
    assert "--seed 2 --rich-brief" in readme
    assert all(f.origin in readme for f in facts)
    assert "with 3 Claude calls" in result.output


@pytest.mark.parametrize("out", [None, NPCS_DIR, NPCS_DIR.parent / "elsewhere"])
def test_a_rich_brief_never_writes_to_content(
    out: Path | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeProvider()
    monkeypatch.setattr(LLMClient, "provider", property(lambda client: fake))
    before = {path: path.read_bytes() for path in NPCS_DIR.rglob("*") if path.is_file()}

    result = runner.invoke(
        create_cli(), ["generate-npcs", "--rich-brief", *(["--out", str(out)] if out else [])]
    )

    assert result.exit_code != 0
    assert "outside content/" in result.output
    assert not fake.requests
    assert {path: path.read_bytes() for path in NPCS_DIR.rglob("*") if path.is_file()} == before
    assert not (NPCS_DIR.parent / "elsewhere").exists()
