from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from simile.cli import create_cli
from simile.llm import FakeProvider, LLMClient
from simile.npc.content import load_npcs

runner = CliRunner()


def test_generate_npcs_writes_the_village(
    residents: Callable[[], FakeProvider], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = residents()
    monkeypatch.setattr("simile.llm.LLMClient", lambda **kwargs: LLMClient(fake, **kwargs))

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
