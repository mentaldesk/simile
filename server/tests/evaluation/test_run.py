import json
from pathlib import Path
from typing import Any

import pytest

from simile.characters.pool import CONTENT_DIR
from simile.evaluation.fake import Stock
from simile.evaluation.report import Run
from simile.evaluation.run import REPLIES, REPORT, Refused, check_writable, choose, evaluate
from simile.evaluation.scenarios import SCENARIOS
from simile.llm import FakeProvider, LLMClient
from simile.memory.store import DEFAULT_PATH
from simile.schema import Character

pytestmark = pytest.mark.anyio


class StandIn(FakeProvider):
    """Counts as Claude for the call count, without calling it."""

    name = "stand-in"


def run(calls: int) -> Run:
    return Run(pool="pool", sample="two", model="m", judge="j", calls=calls)


def test_choose_draws_the_same_sample_for_a_seed(pool: list[Character]) -> None:
    drawn = choose(pool, 10, seed=3)

    assert [c.id for c in drawn] == [c.id for c in choose(pool, 10, seed=3)]
    assert [c.id for c in drawn] == sorted(c.id for c in drawn)
    assert len({c.id for c in drawn}) == 10
    assert [c.id for c in drawn] != [c.id for c in choose(pool, 10, seed=4)]


def test_choose_takes_picks_as_given(pool: list[Character]) -> None:
    a, b = pool[3].id, pool[1].id

    assert [c.id for c in choose(pool, 10, 0, [a, b, a])] == sorted([a, b])
    with pytest.raises(Refused, match="No character nobody"):
        choose(pool, 10, 0, ["nobody"])
    with pytest.raises(Refused, match="between 2 and"):
        choose(pool, len(pool) + 1, 0)


def test_nothing_is_written_in_content_or_the_save_folder(tmp_path: Path) -> None:
    check_writable(tmp_path / "out")
    for folder in (CONTENT_DIR / "npcs", CONTENT_DIR, DEFAULT_PATH.parent / "evaluation"):
        with pytest.raises(Refused):
            check_writable(folder)


async def test_a_run_saves_its_replies_and_counts_its_calls(
    pool: list[Character], embedder: Any, tmp_path: Path
) -> None:
    fake = StandIn(default=Stock())

    result = await evaluate(
        LLMClient(fake), pool[:2], embedder, model="m", judge="j", run=run, out=tmp_path
    )

    assert result.missing == 0 and result.calls == 11 and len(fake.requests) == 11
    assert [r.model for r in fake.requests] == ["m"] * 10 + ["j"]
    assert result.report == (tmp_path / REPORT).read_text(encoding="utf-8")
    assert "Claude calls: 11." in result.report
    saved = json.loads((tmp_path / REPLIES).read_text(encoding="utf-8"))
    assert saved["calls"] == 11
    assert {(r["character"], r["scenario"]) for r in saved["replies"]} == {
        (c.id, s.id) for c in pool[:2] for s in SCENARIOS
    }
    assert all(r["stance"] for r in saved["replies"])

    again = await evaluate(
        LLMClient(fake), pool[:2], embedder, model="m", judge="j", run=run, out=tmp_path
    )

    assert len(fake.requests) == 11
    assert again.report == result.report


async def test_a_run_cut_short_writes_no_report_and_a_rerun_finishes(
    pool: list[Character], embedder: Any, tmp_path: Path
) -> None:
    fake = StandIn(default=Stock())

    cut = await evaluate(
        LLMClient(fake),
        pool[:2],
        embedder,
        model="m",
        judge="j",
        run=run,
        out=tmp_path,
        max_calls=4,
    )

    assert (cut.missing, cut.calls, cut.report) == (6, 4, None)
    assert not (tmp_path / REPORT).exists()
    assert len(json.loads((tmp_path / REPLIES).read_text())["replies"]) == 4

    finished = await evaluate(
        LLMClient(fake), pool[:2], embedder, model="m", judge="j", run=run, out=tmp_path
    )

    assert finished.missing == 0
    assert finished.calls == 11 and len(fake.requests) == 11
    assert "Claude calls: 11." in (finished.report or "")


async def test_fake_calls_are_not_counted_as_claude(pool: list[Character], embedder: Any) -> None:
    result = await evaluate(
        LLMClient(FakeProvider(default=Stock())), pool[:2], embedder, model="m", judge="j", run=run
    )

    assert result.calls == 0


async def test_the_report_shows_every_reply_beside_the_paper_spread(
    pool: list[Character], embedder: Any
) -> None:
    result = await evaluate(
        LLMClient(StandIn(default=Stock())), pool[:2], embedder, model="m", judge="j", run=run
    )

    report = result.report or ""
    assert "| On paper: persona and backstory |" in report
    assert "| On paper: core values (RMS difference) |" in report
    assert "| For scale: replies to different scenarios |" in report
    for scenario in SCENARIOS:
        assert f"## {scenario.title}" in report
        assert f'"{scenario.line}"' in report
    assert "## Honesty" in report
    for character in pool[:2]:
        assert report.count(f"| {character.name}, ") == len(SCENARIOS) + 1
