import json
from pathlib import Path
from typing import Any

import pytest

from simile.characters.pool import CONTENT_DIR
from simile.conversation import ConversationConfig
from simile.evaluation.fake import Stock
from simile.evaluation.report import Run
from simile.evaluation.run import (
    REPLIES,
    REPORT,
    Refused,
    check_writable,
    choose,
    evaluate,
    played,
)
from simile.evaluation.scenarios import SCENARIOS, TEMPTING
from simile.llm import FakeProvider, LLMClient
from simile.memory.store import DEFAULT_PATH
from simile.schema import Character, CoreValue

pytestmark = pytest.mark.anyio

REPLIED = 2 * len(SCENARIOS)


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

    assert result.missing == 0 and result.calls == REPLIED + 1
    assert [r.model for r in fake.requests] == ["m"] * REPLIED + ["j"]
    assert result.report == (tmp_path / REPORT).read_text(encoding="utf-8")
    assert f"Claude calls: {REPLIED + 1}." in result.report
    saved = json.loads((tmp_path / REPLIES).read_text(encoding="utf-8"))
    assert saved["calls"] == REPLIED + 1
    assert {(r["character"], r["scenario"]) for r in saved["replies"]} == {
        (c.id, s.id) for c in pool[:2] for s in SCENARIOS
    }
    assert all(r["stance"] for r in saved["replies"])

    again = await evaluate(
        LLMClient(fake), pool[:2], embedder, model="m", judge="j", run=run, out=tmp_path
    )

    assert len(fake.requests) == REPLIED + 1
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

    assert (cut.missing, cut.calls, cut.report) == (REPLIED - 4, 4, None)
    assert not (tmp_path / REPORT).exists()
    assert len(json.loads((tmp_path / REPLIES).read_text())["replies"]) == 4

    finished = await evaluate(
        LLMClient(fake), pool[:2], embedder, model="m", judge="j", run=run, out=tmp_path
    )

    assert finished.missing == 0
    assert finished.calls == REPLIED + 1 and len(fake.requests) == REPLIED + 1
    assert f"Claude calls: {REPLIED + 1}." in (finished.report or "")


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
    assert "## Humour" in report
    for character in pool[:2]:
        assert report.count(f"| {character.name}, ") == len(SCENARIOS) + 2


async def test_a_run_reuses_another_runs_replies_without_counting_its_calls(
    pool: list[Character], embedder: Any, tmp_path: Path
) -> None:
    fake = StandIn(default=Stock())
    tempting = list(TEMPTING)
    sly = [c for c in pool if c.values[CoreValue.HONESTY] < 0.3][:2]
    always = ConversationConfig(lie_most=1, lie_peak=0.55, lie_bias=1)

    before = await evaluate(
        LLMClient(fake),
        sly,
        embedder,
        model="m",
        judge="j",
        run=run,
        out=tmp_path / "before",
        scenarios=tempting,
        config=ConversationConfig(lie_most=0),
    )
    after = await evaluate(
        LLMClient(fake),
        sly,
        embedder,
        model="m",
        judge="j",
        run=run,
        out=tmp_path / "after",
        scenarios=tempting,
        config=always,
        reuse=tmp_path / "before",
    )

    assert before.calls == 2 * len(tempting) + 1
    assert not any(reply.directed for reply in before.replies)
    assert all(reply.directed for reply in after.replies)
    assert after.calls == 2 * len(tempting) + 1
    again = await evaluate(
        LLMClient(fake),
        sly,
        embedder,
        model="m",
        judge="j",
        run=run,
        out=tmp_path / "again",
        scenarios=tempting,
        config=ConversationConfig(lie_most=0),
        reuse=tmp_path / "after",
    )
    assert again.calls == 0
    assert len(fake.requests) == before.calls + after.calls


def test_played_takes_ids_or_the_tempting_ones() -> None:
    assert played(None) == list(SCENARIOS)
    assert played("tempting") == list(TEMPTING)
    assert [s.id for s in played("lie, favour,lie")] == ["lie", "favour"]
    with pytest.raises(Refused, match="No scenario nowhere"):
        played("favour,nowhere")
