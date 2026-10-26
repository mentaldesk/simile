from datetime import UTC, datetime, timedelta

import pytest

from simile.npc import load_npcs
from simile.player.hours import hours, next_opening
from simile.schema import Shift, Weekday

W = Weekday
NOT_MONDAY = [day for day in Weekday if day is not W.MONDAY]
ODALYS = [
    Shift(days=NOT_MONDAY, start=11, end=14.5),
    Shift(days=NOT_MONDAY, start=17, end=21.5),
]
MONDAY = datetime(2026, 10, 26, tzinfo=UTC)


def at(day: int, hour: int, minute: int = 0) -> datetime:
    """Days after Monday 26 October 2026."""
    return MONDAY + timedelta(days=day, hours=hour, minutes=minute)


@pytest.mark.parametrize(
    ("now", "opens"),
    [
        (at(0, 19, 52), at(1, 11)),
        (at(6, 22), at(8, 11)),
        (at(5, 23, 30), at(6, 11)),
        (at(1, 9), at(1, 11)),
        (at(1, 11), at(1, 17)),
        (at(1, 13), at(1, 17)),
        (at(1, 21, 40), at(2, 11)),
    ],
    ids=[
        "monday_evening_when_she_does_not_work",
        "sunday_night_across_monday",
        "across_midnight",
        "before_the_lunch_shift",
        "as_one_starts",
        "between_shifts",
        "after_the_last",
    ],
)
def test_the_next_opening_is_the_next_shift_to_start(now: datetime, opens: datetime) -> None:
    assert next_opening(ODALYS, now) == opens


def test_a_shop_open_one_day_a_week_opens_again_next_week() -> None:
    mondays = [Shift(days=[W.MONDAY], start=9, end=10)]

    assert next_opening(mondays, at(0, 12)) == at(7, 9)


def test_a_shift_past_midnight_opens_once_not_again_at_midnight() -> None:
    night = [Shift(days=[W.MONDAY], start=20, end=24), Shift(days=[W.TUESDAY], start=0, end=2)]

    assert next_opening(night, at(0, 23)) == at(7, 20)


def test_a_shop_nobody_works_at_never_opens() -> None:
    assert next_opening([], at(0, 12)) is None


def test_a_shop_serves_in_the_shifts_of_whoever_works_there() -> None:
    npcs = load_npcs()

    assert hours("noodle_bar", npcs) == next(n for n in npcs if n.id == "odalys").shifts
    assert hours("noodle_bar", []) == []
    assert hours("coffee_shop", []) == []
