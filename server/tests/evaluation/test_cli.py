import json
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


def test_scenarios_picks_which_to_play() -> None:
    tempting = evaluate("--sample", "2", "--scenarios", "tempting")
    two = evaluate("--sample", "2", "--scenarios", "rent,favour")

    assert tempting.exit_code == 0, tempting.output
    assert "(2 drawn with seed 0), 6 scenarios" in tempting.stdout
    assert "## A stranger asks a favour" not in tempting.stdout
    assert "## Short of money" in two.stdout and "## A stranger asks a favour" in two.stdout
    assert "## Asked to lie" not in two.stdout


def test_unknown_scenarios_are_refused() -> None:
    result = evaluate("--scenarios", "nowhere")

    assert result.exit_code != 0
    assert "No scenario nowhere" in said(result)


def test_no_lies_directs_nobody_and_reuse_takes_another_runs_replies(tmp_path: Path) -> None:
    picks = ["--pick", "grzegorz_pietrzak,marcin_wozniak", "--scenarios", "tempting"]

    honest = evaluate(*picks, "--no-lies", "--out", str(tmp_path / "a"))
    rolled = evaluate(*picks, "--out", str(tmp_path / "b"), "--reuse", str(tmp_path / "a"))

    assert honest.exit_code == 0 and rolled.exit_code == 0, honest.output + rolled.output
    before = json.loads((tmp_path / "a" / REPLIES).read_text())["replies"]
    after = json.loads((tmp_path / "b" / REPLIES).read_text())["replies"]
    assert not any(reply["directed"] for reply in before)
    assert any(reply["directed"] for reply in after)
    assert {reply["key"] for reply in before} & {reply["key"] for reply in after}


def test_no_humour_leaves_it_out_of_the_prompts_but_not_the_report(tmp_path: Path) -> None:
    picks = ["--pick", "chloe_clarke,kamran_malik", "--scenarios", "rain,news"]

    without = evaluate(*picks, "--no-humour", "--out", str(tmp_path / "a"))
    given = evaluate(*picks, "--out", str(tmp_path / "b"), "--reuse", str(tmp_path / "a"))

    assert without.exit_code == 0 and given.exit_code == 0, without.output + given.output
    before = json.loads((tmp_path / "a" / REPLIES).read_text())["replies"]
    after = json.loads((tmp_path / "b" / REPLIES).read_text())["replies"]
    keys = {reply["key"] for reply in before}
    fresh = [reply for reply in after if reply["key"] not in keys]
    assert all(reply["joke_roll"] is None for reply in before)
    assert len(fresh) == 4
    assert all(reply["joke_roll"] is not None for reply in fresh)
    left_out = (tmp_path / "a" / REPORT).read_text(encoding="utf-8")
    assert "The prompts left humour out" in left_out
    assert "| Chloe Clarke, 32, Quantum physicist building gravity sensors | gallows, " in left_out
    assert "The prompts gave each character their humour." in (tmp_path / "b" / REPORT).read_text(
        encoding="utf-8"
    )
