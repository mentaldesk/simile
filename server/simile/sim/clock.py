import asyncio
import time
from datetime import UTC, datetime, timedelta
from typing import Protocol


def eight_this_morning() -> datetime:
    return datetime.now(UTC).replace(hour=8, minute=0, second=0, microsecond=0)


class Clock:
    def __init__(self, start: datetime | None = None, speed: float = 1.0) -> None:
        self.now = start or eight_this_morning()
        self.speed = speed

    @property
    def now(self) -> datetime:
        return self._now

    @now.setter
    def now(self, now: datetime) -> None:
        if now.tzinfo is None:
            raise ValueError(f"sim time must be timezone-aware, not {now!r}")
        self._now = now.astimezone(UTC)

    @property
    def speed(self) -> float:
        return self._speed

    @speed.setter
    def speed(self, speed: float) -> None:
        if speed <= 0:
            raise ValueError(f"speed must be positive, not {speed}")
        self._speed = speed

    @property
    def time_of_day(self) -> float:
        midnight = self.now.replace(hour=0, minute=0, second=0, microsecond=0)
        return (self.now - midnight) / timedelta(hours=1)

    def advance(self, dt: float) -> None:
        self._now += timedelta(seconds=dt)

    def __str__(self) -> str:
        return f"{self.now:%Y-%m-%d %H:%M:%S}"


class WallClock(Protocol):
    def now(self) -> float: ...

    async def sleep(self, seconds: float) -> None: ...


class RealWallClock:
    def now(self) -> float:
        return time.monotonic()

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


class FakeWallClock:
    def __init__(self, start: float = 0.0) -> None:
        self._now = start

    def now(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds

    async def sleep(self, seconds: float) -> None:
        self.advance(seconds)
        await asyncio.sleep(0)
