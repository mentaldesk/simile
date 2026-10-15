import asyncio
from datetime import UTC, datetime

import pytest
from typer.testing import CliRunner

from simile.behaviour.simulate import ranks, report, simulate, spearman
from simile.cli import create_cli

runner = CliRunner()


def test_nobody_is_out_in_the_small_hours() -> None:
    start = datetime(2026, 1, 1, 2, 30, tzinfo=UTC)

    observer, _ = asyncio.run(simulate(1, start=start))

    assert sum(observer.out.values()) == 0
    assert sum(observer.samples.values()) == 61
    assert observer.by_hour[3]["home"] == 10 * observer.samples[3]


def test_a_morning_gets_people_out_and_about() -> None:
    start = datetime(2026, 1, 1, 9, tzinfo=UTC)

    observer, seconds = asyncio.run(simulate(1, start=start, seed=1))
    summary = report(observer, 1, start, 1, seconds)

    assert sum(observer.out.values()) > 0
    assert sum(sum(goals.values()) for goals in observer.goals.values()) > 10
    assert "| 09 |" in summary
    assert "Out of home at 03:00: 0." in summary


def test_the_same_seed_gives_the_same_summary() -> None:
    start = datetime(2026, 1, 1, 9, tzinfo=UTC)

    def summary(seed: int) -> str:
        observer, _ = asyncio.run(simulate(0.5, start=start, seed=seed))
        return report(observer, 0.5, start, seed, 0)

    assert summary(4) == summary(4)


def test_cli_prints_the_summary() -> None:
    result = runner.invoke(
        create_cli(), ["behaviour", "simulate", "--hours", "1", "--start", "2.5"]
    )

    assert result.exit_code == 0, result.output
    assert "Simulated 1 sim hours from 2026-01-01 02:30 UTC, seed 0" in result.output
    assert "Out of home at 03:00: 0." in result.output


def test_spearman_ranks_ties_together() -> None:
    assert ranks([3.0, 1.0, 3.0, 2.0]) == [2.5, 0, 2.5, 1]
    assert spearman([1, 2, 3], [10, 20, 30]) == pytest.approx(1)
    assert spearman([1, 2, 3], [3, 2, 1]) == pytest.approx(-1)
    assert spearman([1, 1, 1], [1, 2, 3]) == 0
