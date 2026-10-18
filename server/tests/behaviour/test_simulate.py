import asyncio
from collections import Counter
from datetime import UTC, datetime, timedelta

import pytest
from typer.testing import CliRunner

from simile.behaviour import Need
from simile.behaviour.simulate import ranks, report, simulate, spearman
from simile.cli import create_cli
from simile.npc import load_npcs
from simile.schema import Craft, Medium
from simile.world.map import load_map

runner = CliRunner()


def test_nobody_is_out_in_the_small_hours() -> None:
    start = datetime(2026, 1, 1, 2, 30, tzinfo=UTC)

    observer, _ = asyncio.run(simulate(1, start=start))

    assert sum(observer.out.values()) == 0
    assert sum(observer.samples.values()) == 61
    assert observer.by_hour[3]["home"] == len(load_npcs()) * observer.samples[3]


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


def test_cli_with_talk_accepts_requests_and_reports_conversations() -> None:
    declined = runner.invoke(
        create_cli(), ["behaviour", "simulate", "--hours", "1", "--start", "11"]
    )
    accepted = runner.invoke(
        create_cli(), ["behaviour", "simulate", "--hours", "1", "--start", "11", "--talk", "3"]
    )

    assert accepted.exit_code == 0, accepted.output
    assert "**Conversations.**" not in declined.output
    conversations = accepted.output.split("**Conversations.**")[1]
    assert "lasted 3 minutes" in conversations
    assert "| desmond | 0.50 |" in conversations


def test_spearman_ranks_ties_together() -> None:
    assert ranks([3.0, 1.0, 3.0, 2.0]) == [2.5, 0, 2.5, 1]
    assert spearman([1, 2, 3], [10, 20, 30]) == pytest.approx(1)
    assert spearman([1, 2, 3], [3, 2, 1]) == pytest.approx(-1)
    assert spearman([1, 1, 1], [1, 2, 3]) == 0


def test_reports_the_works_residents_with_a_craft_make() -> None:
    start = datetime(2026, 1, 1, 8, tzinfo=UTC)
    media = [Medium.MURAL, Medium.WRITING, None]
    npcs = [
        npc.model_copy(update={"craft": Craft(medium=medium, form="x") if medium else None})
        for npc, medium in zip(load_npcs(), media * 4, strict=False)
    ]

    observer, seconds = asyncio.run(simulate(12, start=start, npcs=npcs))
    summary = report(observer, 12, start, 0, seconds)

    places = {place for made in observer.works.values() for place in made}
    walls = {wall.id for wall in load_map().murals}
    assert sum(sum(made.values()) for made in observer.works.values()) >= 3
    assert places & walls and places - walls
    works = summary.split("**Works.**")[1].split("\n\n**")[0]
    listed = {npc.id for npc in npcs if f"| {npc.id} |" in works}
    assert listed == {npc.id for npc in npcs if npc.craft}


def test_a_day_has_meals_at_mealtimes_and_no_need_runs_away() -> None:
    start = datetime(2026, 1, 1, 8, tzinfo=UTC)

    observer, seconds = asyncio.run(simulate(24, start=start, talk=3))
    summary = report(observer, 24, start, 0, seconds)

    hours = Counter(meal.at.hour for meal in observer.meals)
    assert len(observer.meals) >= 2 * len(observer.behaviour.npcs)
    assert not any(hours[hour] for hour in range(0, 5))
    for meal in ((5, 10), (11, 15), (17, 22)):
        assert sum(hours[hour] for hour in range(*meal)) > 0, meal
    for need in (Need.HUNGER, Need.BLADDER, Need.HYGIENE):
        awake = [level for level, up in observer.needs[need] if up]
        assert sum(level >= 0.9 for level in awake) / len(awake) < 0.02, need
    assert "**Time by place.**" in summary and "**Meals.**" in summary
    assert "| hunger |" in summary and "| hygiene |" in summary


def test_a_day_has_shifts_and_money_that_add_up() -> None:
    start = datetime(2026, 1, 1, 6, tzinfo=UTC)

    observer, seconds = asyncio.run(simulate(24, start=start))
    summary = report(observer, 24, start, 0, seconds)

    economy = observer.economy
    assert economy is not None
    worked = {turn.npc for turn in economy.turns if turn.arrived}
    assert {"mirela", "ingrid", "lachlan"} <= worked
    assert economy.ledger.gap(economy.money) == pytest.approx(0, abs=1e-6)
    assert all(amount > 0 for amount in economy.money.values())
    headings = ("**Shifts.**", "**Shops.**", "**Fridges.**", "**Money.**", "**Hunger.**")
    for heading in (*headings, "**Where the money went.**"):
        assert heading in summary


def test_the_shops_feed_people_only_while_their_keepers_are_there() -> None:
    start = datetime(2026, 1, 3, 6, tzinfo=UTC)

    observer, _ = asyncio.run(simulate(24, start=start, seed=2))

    economy = observer.economy
    assert economy is not None
    there = {
        keeper: [(t.arrived, t.end) for t in economy.turns if t.npc == keeper and t.arrived]
        for keeper in economy.keepers.values()
    }
    out = [meal for meal in observer.meals if meal.place in economy.keepers]
    assert {meal.place for meal in out} == {"coffee_shop", "noodle_bar"}
    for meal in out:
        open_at = there[economy.keepers[meal.place]]
        assert any(a <= meal.at <= end + timedelta(minutes=1) for a, end in open_at), meal
    assert economy.cooked and all(batch.shop == "noodle_bar" for batch in economy.cooked)
