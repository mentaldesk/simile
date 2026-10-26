from collections.abc import Iterable
from datetime import datetime, timedelta

from simile.schema import Id, Npc, Shift, Weekday

HOUR = timedelta(hours=1)
WEEK = 7


def hours(place: Id, npcs: Iterable[Npc]) -> list[Shift]:
    """When a shop serves: the shifts of whoever works there."""
    return [shift for npc in npcs if npc.workplace == place for shift in npc.shifts]


def next_opening(shifts: list[Shift], now: datetime) -> datetime | None:
    """When the first shift after `now` starts, leaving out one that carries on from 24 the day
    before. None without shifts."""
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    for offset in range(WEEK + 1):
        day = midnight + timedelta(days=offset)
        weekday, before = Weekday.of(day), Weekday.of(day - timedelta(days=1))
        carried = any(before in shift.days and shift.end == 24 for shift in shifts)
        starts = sorted(
            day + shift.start * HOUR
            for shift in shifts
            if weekday in shift.days and not (shift.start == 0 and carried)
        )
        if (start := next((start for start in starts if start > now), None)) is not None:
            return start
    return None
