from collections.abc import Callable

import pytest
from typer.testing import CliRunner

from simile.casting.variety import average, variety
from simile.cli import create_cli
from simile.schema import Character

type Make = Callable[..., Character]


def test_variety_counts_families_making_repeats_elders_and_ages(make: Make) -> None:
    residents = [
        make("a", occupation="Barista", birth_year=2000),
        make("b", occupation="Waiter", birth_year=1990),
        make("c", occupation="Retired welder", birth_year=1950),
        make("d", occupation="Toolmaker", birth_year=1960),
        make("e", occupation="Board game designer", birth_year=1980),
        make("f", occupation="Engineering student", birth_year=2006),
    ]

    found = variety(residents, 2026)
    without_the_barista = variety(residents, 2026, roles={"a"})

    assert (found.families, found.making, found.repeats, found.elders) == (4, 4, 2, 2)
    assert (found.youngest, found.oldest) == (20, 76)
    assert found.age_spread == pytest.approx(20.29, abs=0.01)
    assert without_the_barista.repeats == 1
    assert average([found, without_the_barista])["repeats"] == 1.5


def test_cast_variety_reports_each_seed_and_the_mean() -> None:
    result = CliRunner().invoke(create_cli(), ["cast-variety", "--seeds", "2", "--count", "6"])

    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert lines[0].split()[:3] == ["seed", "families", "making"]
    assert [line.split()[0] for line in lines[1:]] == ["0", "1", "mean"]
