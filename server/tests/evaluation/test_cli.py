import re
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from simile.characters.pool import CONTENT_DIR
from simile.cli import create_cli
from simile.evaluation.run import REPLIES, REPORT

runner = CliRunner()
COLOUR = re.compile(r"\x1b\[[0-9;]*m")


class NoClaude:
    def __init__(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("tried to reach Claude")


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch, embedder: object) -> None:
    monkeypatch.setattr("simile.characters.novelty.LocalEmbedder", lambda: embedder)
    monkeypatch.setattr("simile.llm.claude_code.ClaudeCodeProvider", NoClaude)


def said(result: Result) -> str:
    return " ".join(COLOUR.sub("", result.output).replace("│", " ").split())


def snapshot() -> dict[Path, bytes]:
    return {path: path.read_bytes() for path in CONTENT_DIR.rglob("*") if path.is_file()}


def evaluate(*args: str) -> Result:
    return runner.invoke(create_cli(), ["evaluate", "characters", *args])


def test_without_claude_stock_replies_stand_in_and_the_report_goes_to_stdout() -> None:
    before = snapshot()

    result = evaluate("--sample", "3", "--seed", "1")

    assert result.exit_code == 0, result.output
    assert result.stdout.startswith("# Behavioural evaluation of characters")
    assert "Stock replies and stances stood in for Claude" in result.stdout
    assert "3 characters from `content/characters/pool` (3 drawn with seed 1)" in result.stdout
    assert snapshot() == before


def test_out_gets_the_report_and_the_replies(tmp_path: Path) -> None:
    result = evaluate("--pick", "chloe_clarke,kamran_malik", "--out", str(tmp_path))

    assert result.exit_code == 0, result.output
    report = (tmp_path / REPORT).read_text(encoding="utf-8")
    assert "Chloe Clarke, 32, Quantum physicist building gravity sensors" in report
    assert "chloe_clarke, kamran_malik" in report
    assert (tmp_path / REPLIES).exists()
    assert not result.stdout


@pytest.mark.parametrize("folder", [CONTENT_DIR / "evaluation", CONTENT_DIR / "npcs"])
def test_out_in_content_is_refused(folder: Path) -> None:
    before = snapshot()

    result = evaluate("--sample", "2", "--out", str(folder))

    assert result.exit_code != 0
    assert "won't write in" in said(result)
    assert snapshot() == before


def test_claude_under_the_fake_llm_still_uses_stock_replies() -> None:
    result = evaluate("--sample", "2", "--claude")

    assert result.exit_code == 0, result.output
    assert "SIMILE_LLM=fake, so stock replies stand in for Claude." in result.output
    assert "Stock replies and stances stood in" in result.stdout


def test_claude_takes_only_a_small_sample(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SIMILE_LLM")

    result = evaluate("--sample", "11", "--claude")

    assert result.exit_code != 0
    assert "at most 10 characters with --claude, not 11" in said(result)


def test_unknown_picks_are_refused() -> None:
    result = evaluate("--pick", "nobody")

    assert result.exit_code != 0
    assert "No character nobody in the pool" in said(result)
