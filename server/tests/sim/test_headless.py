import asyncio
import logging
import os
import signal
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from typer.testing import CliRunner

from simile.cli import create_cli
from simile.sim import Clock, EntityMoved, FakeWallClock, World
from simile.sim.headless import run_headless

MakeVillage = Callable[..., str]

START = datetime(2026, 1, 1, 8, tzinfo=UTC)


def world_at_start(speed: float = 1) -> tuple[World, FakeWallClock]:
    wall = FakeWallClock()
    return World(Clock(START, speed), wall), wall


class Walker:
    def __init__(self, world: World) -> None:
        self.world = world

    def tick(self, dt: float) -> None:
        if (self.world.clock.now - START) % timedelta(minutes=20) == timedelta(0):
            self.world.bus.publish(EntityMoved("ada", 1.0, 2.0))


def test_runs_for_the_given_sim_hours_and_logs_events(
    make_village: MakeVillage, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="simile.sim")
    world, wall = world_at_start(speed=10)

    asyncio.run(run_headless(world, timedelta(hours=1), make_village({"town": [Walker]})))

    assert world.clock.now == START + timedelta(hours=1)
    assert wall.now() == pytest.approx(3600 / 10)
    moved = "EntityMoved(entity='ada', x=1.0, y=2.0)"
    assert caplog.messages == [
        "2026-01-01 08:00:00  Running at 10x",
        f"2026-01-01 08:20:00  {moved}",
        f"2026-01-01 08:40:00  {moved}",
        "2026-01-01 09:00:00",
        f"2026-01-01 09:00:00  {moved}",
        "2026-01-01 09:00:00  Stopped",
    ]


@pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM])
def test_stops_cleanly_on_a_signal(
    sig: signal.Signals, make_village: MakeVillage, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="simile.sim")

    class Interrupter:
        def __init__(self, world: World) -> None:
            self.world = world

        def tick(self, dt: float) -> None:
            if self.world.clock.now == START + timedelta(seconds=10):
                os.kill(os.getpid(), sig)

    world, _ = world_at_start()
    asyncio.run(run_headless(world, None, make_village({"town": [Interrupter]})))

    assert timedelta(seconds=10) <= world.clock.now - START < timedelta(seconds=11)
    assert caplog.messages[-1].endswith("Stopped")
    assert signal.getsignal(signal.SIGINT) is signal.default_int_handler
    assert signal.getsignal(signal.SIGTERM) is signal.SIG_DFL


SIGINT_ON_SHUTDOWN = (
    "import os, signal\n"
    "from contextlib import asynccontextmanager\n"
    "@asynccontextmanager\n"
    "async def lifespan(app):\n"
    "    yield\n"
    "    os.kill(os.getpid(), signal.SIGINT)\n"
)


def test_a_second_sigint_during_shutdown_interrupts_it(make_village: MakeVillage) -> None:
    class Interrupter:
        def __init__(self, world: World) -> None:
            self.world = world

        def tick(self, dt: float) -> None:
            if self.world.clock.now == START + timedelta(seconds=10):
                os.kill(os.getpid(), signal.SIGINT)

    package = make_village({"town": [Interrupter]}, {"voice/lifespan.py": SIGINT_ON_SHUTDOWN})
    world, _ = world_at_start()

    with pytest.raises(KeyboardInterrupt):
        asyncio.run(run_headless(world, None, package))

    assert signal.getsignal(signal.SIGINT) is signal.default_int_handler


def test_a_failing_system_ends_the_run_with_its_error(make_village: MakeVillage) -> None:
    class Broken:
        def __init__(self, world: World) -> None:
            pass

        def tick(self, dt: float) -> None:
            raise RuntimeError("boom")

    world, _ = world_at_start()
    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(run_headless(world, None, make_village({"town": [Broken]})))


def test_headless_command_passes_speed_and_duration(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[float, timedelta | None]] = []

    async def fake_run_headless(world: World, duration: timedelta | None) -> None:
        calls.append((world.clock.speed, duration))

    monkeypatch.setattr("simile.sim.headless.run_headless", fake_run_headless)

    result = CliRunner().invoke(create_cli(), ["headless", "--speed", "10", "--duration", "0.5"])

    assert result.exit_code == 0, result.output
    assert calls == [(10, timedelta(minutes=30))]


def test_headless_command_exits_130_when_interrupted(monkeypatch: pytest.MonkeyPatch) -> None:
    async def interrupted(world: World, duration: timedelta | None) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr("simile.sim.headless.run_headless", interrupted)

    result = CliRunner().invoke(create_cli(), ["headless"])

    assert result.exit_code == 130


def test_headless_command_rejects_a_speed_of_zero() -> None:
    result = CliRunner().invoke(create_cli(), ["headless", "--speed", "0"])

    assert result.exit_code == 2
    assert "must be more than 0" in result.output
