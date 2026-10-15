import asyncio
from datetime import UTC, datetime, timedelta, timezone

import pytest

from simile.sim import Clock, FakeWallClock

START = datetime(2026, 1, 1, 8, tzinfo=UTC)


def test_starts_at_eight_this_morning_utc() -> None:
    clock = Clock()

    assert clock.now.tzinfo is UTC
    assert clock.now.date() == datetime.now(UTC).date()
    assert clock.time_of_day == 8
    assert str(clock) == f"{clock.now:%Y-%m-%d} 08:00:00"


def test_advances_past_midnight() -> None:
    clock = Clock(START)

    clock.advance(16 * 3600 + 61.5)

    assert clock.now == datetime(2026, 1, 2, 0, 1, 1, 500_000, tzinfo=UTC)
    assert clock.time_of_day == pytest.approx(61.5 / 3600)
    assert str(clock) == "2026-01-02 00:01:01"


def test_tenths_of_a_second_add_up_exactly() -> None:
    clock = Clock(START)

    for _ in range(36_000):
        clock.advance(0.1)

    assert clock.now == START + timedelta(hours=1)


def test_converts_other_time_zones_to_utc() -> None:
    clock = Clock(datetime(2026, 1, 1, 18, tzinfo=timezone(timedelta(hours=10))))

    assert clock.now == START
    assert clock.now.tzinfo is UTC


def test_rejects_naive_datetimes() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        Clock(datetime(2026, 1, 1, 8))
    with pytest.raises(ValueError, match="timezone-aware"):
        Clock(START).now = datetime(2026, 1, 1, 8)


@pytest.mark.parametrize("speed", [0, -1])
def test_speed_must_be_positive(speed: float) -> None:
    with pytest.raises(ValueError):
        Clock(START, speed)
    with pytest.raises(ValueError):
        Clock(START).speed = speed


def test_fake_wall_clock_sleeps_instantly() -> None:
    wall = FakeWallClock()

    asyncio.run(wall.sleep(5))
    wall.advance(1.5)

    assert wall.now() == 6.5
