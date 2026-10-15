import asyncio
import logging
import signal
from datetime import datetime, timedelta

from simile.app import create_app
from simile.sim.clock import Clock
from simile.sim.events import Event
from simile.sim.world import World

logger = logging.getLogger(__name__)

STOP_SIGNALS = (signal.SIGINT, signal.SIGTERM)


def hour_of(clock: Clock) -> datetime:
    return clock.now.replace(minute=0, second=0, microsecond=0)


class HourlyLog:
    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self.hour = hour_of(clock)

    def tick(self, dt: float) -> None:
        if hour_of(self.clock) != self.hour:
            self.hour = hour_of(self.clock)
            logger.info(f"{self.clock}")


async def run_headless(
    world: World, duration: timedelta | None = None, package: str = "simile"
) -> None:
    app = create_app(package)
    app.state.world = world
    app.state.headless = True
    world.bus.subscribe(Event, lambda event: logger.info(f"{world.clock}  {event}"))
    world.loop.register(HourlyLog(world.clock))

    loop = asyncio.get_running_loop()

    def restore_signals() -> None:
        for sig in STOP_SIGNALS:
            loop.remove_signal_handler(sig)

    def stop() -> None:
        world.loop.stop()
        restore_signals()

    for sig in STOP_SIGNALS:
        loop.add_signal_handler(sig, stop)
    try:
        async with app.router.lifespan_context(app):
            logger.info(f"{world.clock}  Running at {world.clock.speed:g}x")
            await world.loop.run(duration)
    finally:
        restore_signals()
    logger.info(f"{world.clock}  Stopped")
