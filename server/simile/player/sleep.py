import logging
from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, Field

from simile.behaviour.config import DEFAULT_CONFIG as BEHAVIOUR
from simile.player.health import Health
from simile.sim import Clock

logger = logging.getLogger(__name__)

NIGHT_STARTS = BEHAVIOUR.bedtime_range[0]
"""The earliest bedtime any resident can have, 21:00, as the client's `NIGHT.from`."""


class SleepConfig(BaseModel):
    """When a rest in bed sleeps until morning, and how fast the night goes by."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    night_starts: float = Field(
        default=NIGHT_STARTS, ge=12, lt=24, description="The hour night starts."
    )
    night_ends: float = Field(default=6.0, gt=0, lt=12, description="The hour night ends.")
    morning: float = Field(
        default=7.0, gt=0, lt=12, description="The hour a night's sleep ends and they get up."
    )
    speed: float = Field(
        default=3600.0,
        gt=0,
        description="The clock's speed while they sleep: an hour a real second, as fast as the "
        "village's ticks keep up with.",
    )


DEFAULT_SLEEP = SleepConfig()


class Sleep:
    """Resting in bed at night sleeps until morning: once they've lain down the clock runs at
    `speed` until `morning`, when they get up, or until the rest ends or the client leaves first.
    Tick it on the sim loop after `Health`."""

    def __init__(
        self,
        health: Health,
        clock: Clock,
        *,
        playing: Callable[[], bool] = lambda: True,
        config: SleepConfig = DEFAULT_SLEEP,
    ) -> None:
        self.health = health
        self.clock = clock
        self.playing = playing
        self.config = config
        self.skipping = False

    def night(self) -> bool:
        """Whether a rest now sleeps until morning: from `night_starts` until `night_ends`."""
        hour = self.clock.time_of_day
        return hour >= self.config.night_starts or hour < self.config.night_ends

    def tick(self, dt: float) -> None:
        if self.skipping:
            if not self.health.sleeping() or not self.playing():
                self._stop()
            elif self.config.morning <= self.clock.time_of_day < self.config.night_starts:
                self._stop()
                self.health.rest(False)
        elif self.health.sleeping() and self.health.lain_down() and self.playing():
            self.skipping = True
            self.clock.skip(self.config.speed)
            logger.info("%s  The player sleeps until morning", self.clock)

    def _stop(self) -> None:
        self.skipping = False
        self.clock.resume()
        logger.info("%s  The player's sleep ends", self.clock)
