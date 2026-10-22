from datetime import UTC, datetime

import pytest

from simile.economy import OUTSIDE, PLAYER, Entry, Kind, Ledger

NOW = datetime(2026, 1, 1, 12, tzinfo=UTC)


def entry(kind: Kind, amount: float, payer: str, payee: str, place: str | None = None) -> Entry:
    return Entry(at=NOW, kind=kind, amount=amount, payer=payer, payee=payee, place=place)


def test_money_in_less_money_out_is_the_change_in_what_residents_hold() -> None:
    ledger = Ledger({"ana": 100.0, "bea": 50.0})
    for item in (
        entry(Kind.WAGE, 80, OUTSIDE, "ana"),
        entry(Kind.PENSION, 40, OUTSIDE, "bea"),
        entry(Kind.RENT, 30, "ana", OUTSIDE),
        entry(Kind.PURCHASE, 8, "ana", "bea", "noodle_bar"),
        entry(Kind.SUPPLIES, 2.8, "bea", OUTSIDE, "noodle_bar"),
        entry(Kind.GROCERIES, 2.5, "bea", OUTSIDE),
    ):
        ledger.record(item)

    held = ledger.held()

    assert held == pytest.approx({"ana": 142.0, "bea": 92.7})
    assert ledger.came_in() == 120
    assert ledger.went_out() == pytest.approx(35.3)
    assert ledger.gap(held) == pytest.approx(0)
    assert ledger.by_kind()[Kind.PURCHASE] == 8


def test_money_that_moves_outside_the_ledger_shows_as_a_gap() -> None:
    ledger = Ledger({"ana": 100.0})
    ledger.record(entry(Kind.WAGE, 10, OUTSIDE, "ana"))

    assert ledger.gap({"ana": 110.0}) == pytest.approx(0)
    assert ledger.gap({"ana": 125.0}) == pytest.approx(15)


def test_an_entry_moves_some_money() -> None:
    with pytest.raises(ValueError, match="greater than 0"):
        entry(Kind.RENT, 0, "ana", OUTSIDE)
    assert Entry.model_validate_json(entry(Kind.RENT, 30, "ana", OUTSIDE).model_dump_json())


def test_the_players_money_is_in_the_ledger_but_not_in_what_residents_hold() -> None:
    ledger = Ledger({"ana": 100.0})
    for item in (
        entry(Kind.SALVAGE, 23, OUTSIDE, PLAYER, "scrap_stall"),
        entry(Kind.FOUND, 25, OUTSIDE, PLAYER, "metro_secret_stairwell"),
        entry(Kind.PURCHASE, 10, PLAYER, "ana", "noodle_bar"),
        entry(Kind.SUPPLIES, 3, "ana", OUTSIDE, "noodle_bar"),
    ):
        ledger.record(item)

    assert ledger.held() == {"ana": 107.0}
    assert (ledger.came_in(), ledger.went_out()) == (10, 3)
    assert ledger.gap({"ana": 107.0}) == pytest.approx(0)
    assert ledger.net(PLAYER) == 38
    assert ledger.net("ana") == 7
    assert ledger.by_kind()[Kind.SALVAGE] == 23
