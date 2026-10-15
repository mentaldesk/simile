import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from simile.sim import STEP, Clock, FakeWallClock, System, World
from simile.sim.loop import MAX_LAG

START = datetime(2026, 1, 1, 8, tzinfo=UTC)
MINUTE = timedelta(minutes=1)
TICKS_PER_MINUTE = round(60 / STEP)


def at(seconds: float) -> datetime:
    return START + timedelta(seconds=seconds)


def world_at_start(speed: float = 1) -> tuple[World, FakeWallClock]:
    wall = FakeWallClock()
    return World(Clock(START, speed), wall), wall


class Recorder:
    def __init__(self, world: World) -> None:
        self.world = world
        self.ticks: list[tuple[datetime, float]] = []
        self.wall_times: list[float] = []

    def tick(self, dt: float) -> None:
        self.ticks.append((self.world.clock.now, dt))
        self.wall_times.append(self.world.loop.wall.now())


def run_world(speed: float, duration: timedelta, *systems: System) -> Recorder:
    world, _ = world_at_start(speed)
    recorder = Recorder(world)
    for system in (recorder, *systems):
        world.loop.register(system)
    asyncio.run(world.loop.run(duration))
    return recorder


@pytest.mark.parametrize("speed", [1, 10])
def test_no_op_world_ticks_deterministically(speed: float) -> None:
    recorder = run_world(speed, MINUTE)

    ticks = range(1, TICKS_PER_MINUTE + 1)
    assert recorder.ticks == [(START + n * timedelta(seconds=STEP), STEP) for n in ticks]
    assert recorder.wall_times == pytest.approx([n * STEP / speed for n in ticks])
    rerun = run_world(speed, MINUTE)
    assert (rerun.ticks, rerun.wall_times) == (recorder.ticks, recorder.wall_times)


def test_speed_only_changes_how_fast_the_world_runs() -> None:
    assert run_world(1, MINUTE).ticks == run_world(10, MINUTE).ticks


def test_systems_tick_in_registration_order() -> None:
    world, _ = world_at_start()
    calls: list[str] = []

    class Named:
        def __init__(self, name: str) -> None:
            self.name = name

        def tick(self, dt: float) -> None:
            calls.append(self.name)

    world.loop.register(Named("first"))
    world.loop.register(Named("second"))

    world.loop.tick()
    world.loop.tick()

    assert calls == ["first", "second", "first", "second"]
    assert world.clock.now == at(2 * STEP)


def test_a_system_registered_mid_run_ticks_from_the_next_tick() -> None:
    world, _ = world_at_start()
    late = Recorder(world)

    class Registrar:
        def tick(self, dt: float) -> None:
            if world.clock.now == at(STEP):
                world.loop.register(late)

    world.loop.register(Registrar())
    asyncio.run(world.loop.run(timedelta(seconds=3 * STEP)))

    assert [now for now, _ in late.ticks] == [at(2 * STEP), at(3 * STEP)]


def test_changing_speed_mid_run_changes_the_pace() -> None:
    world, wall = world_at_start()

    class SpeedUp:
        def tick(self, dt: float) -> None:
            if world.clock.now == at(10):
                world.clock.speed = 10

    world.loop.register(SpeedUp())
    asyncio.run(world.loop.run(timedelta(seconds=20)))

    assert wall.now() == pytest.approx(10 + 10 / 10)


@pytest.mark.parametrize(("stall", "behind"), [(0.5, 0.0), (5.0, 5.0 - MAX_LAG)])
def test_catches_up_after_a_slow_tick_up_to_max_lag(stall: float, behind: float) -> None:
    world, wall = world_at_start()

    class Slow:
        def tick(self, dt: float) -> None:
            if world.clock.now == at(1):
                wall.advance(stall)

    world.loop.register(Slow())
    asyncio.run(world.loop.run(timedelta(seconds=10)))

    assert wall.now() == pytest.approx(10 + behind)


def test_stop_ends_the_run_after_the_current_tick() -> None:
    world, _ = world_at_start()

    class Stopper:
        def tick(self, dt: float) -> None:
            if world.clock.now == at(1):
                world.loop.stop()

    world.loop.register(Stopper())
    asyncio.run(world.loop.run())

    assert world.clock.now == at(1)


def test_stop_before_running_means_run_returns_at_once() -> None:
    world, _ = world_at_start()

    world.loop.stop()
    asyncio.run(world.loop.run())

    assert world.clock.now == START


def test_a_failing_system_stops_the_run() -> None:
    class Broken:
        def tick(self, dt: float) -> None:
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        run_world(1, MINUTE, Broken())
