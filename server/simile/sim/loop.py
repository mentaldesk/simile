from datetime import timedelta
from typing import Protocol

from simile.sim.clock import Clock, RealWallClock, WallClock

STEP = 0.1
MAX_LAG = 1.0


class System(Protocol):
    def tick(self, dt: float) -> None: ...


class TickLoop:
    def __init__(self, clock: Clock, wall: WallClock | None = None, step: float = STEP) -> None:
        self.clock = clock
        self.wall = wall or RealWallClock()
        self.step = step
        self._systems: list[System] = []
        self._stopped = False

    def register(self, system: System) -> None:
        self._systems.append(system)

    def tick(self) -> None:
        self.clock.advance(self.step)
        for system in tuple(self._systems):
            system.tick(self.step)

    async def run(self, duration: timedelta | None = None) -> None:
        end = None if duration is None else self.clock.now + duration
        deadline = self.wall.now()
        while not self._stopped and (end is None or self.clock.now < end):
            deadline = max(deadline, self.wall.now() - MAX_LAG) + self.step / self.clock.speed
            await self.wall.sleep(max(deadline - self.wall.now(), 0.0))
            if not self._stopped:
                self.tick()

    def stop(self) -> None:
        self._stopped = True
