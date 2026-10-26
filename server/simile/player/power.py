import logging
from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, Field

from simile.schema import LEGS, POWER_CELLS, Bionic, Body, Player
from simile.sim import Clock

logger = logging.getLogger(__name__)

HOUR = 3600.0


class PowerConfig(BaseModel):
    """How fast a power cell runs down, and how many bionics each grade runs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    drain: float = Field(
        default=0.2,
        gt=0,
        description="How much of a full cell it uses each sim hour while someone's playing, with "
        "no other bionic fitted: five hours.",
    )
    per_bionic: float = Field(
        default=0.1,
        ge=0,
        description="How much more it uses each sim hour for each other bionic fitted: with "
        "three, two hours.",
    )
    waking: float = Field(
        default=0.25, gt=0, le=1, description="Their power when they wake after it ran flat."
    )
    runs: dict[Bionic, int] = Field(
        default={Bionic.POWER_CELL: 3, Bionic.POWER_CELL_2: 4, Bionic.POWER_CELL_3: 5},
        description="How many other bionics each grade of cell runs. The clinic fits none past it.",
    )


DEFAULT_POWER = PowerConfig()


def cell_in(body: Body) -> Bionic | None:
    """The power cell in their stomach, if there is one."""
    return body.stomach if body.stomach in POWER_CELLS else None


def others(body: Body) -> list[Bionic]:
    """Every bionic the cell runs: all fitted but the cell and stage 1's legs, which need none."""
    return [bionic for bionic in body.bionics if bionic not in POWER_CELLS + LEGS]


def runs(body: Body, bionic: Bionic, config: PowerConfig = DEFAULT_POWER) -> bool:
    """Whether their cell would still run every other bionic once `bionic` is fitted. True
    without a cell, since a recipe's `after` says what needs one, and for stage 1's legs."""
    if bionic in POWER_CELLS:
        return len(others(body)) <= config.runs[bionic]
    cell = cell_in(body)
    if cell is None or bionic in LEGS:
        return True
    upgrade = any(getattr(body, part) in bionic.line for part in bionic.replaces)
    return len(others(body)) + (0 if upgrade else 1) <= config.runs[cell]


class Power:
    """The player's power cell, once one is fitted: drains faster with each bionic, charges at a
    plug, and collapses them when flat. Tick it on the sim loop."""

    def __init__(
        self,
        player: Player,
        clock: Clock,
        *,
        charging: Callable[[float], float] = lambda dt: 0.0,
        playing: Callable[[], bool] = lambda: True,
        collapse: Callable[[], None] = lambda: None,
        config: PowerConfig = DEFAULT_POWER,
    ) -> None:
        self.player = player
        self.clock = clock
        self.charging = charging
        """How much of a full charge a plug gives them in a tick: the lamp's."""
        self.playing = playing
        self.collapse = collapse
        self.config = config

    def drain(self) -> float:
        """How much of a full cell they use each sim hour, with what's fitted now."""
        return self.config.drain + self.config.per_bionic * len(others(self.player.body))

    def tick(self, dt: float) -> None:
        if cell_in(self.player.body) is None or not self.playing():
            return
        if gained := self.charging(dt):
            self.player.power = min(self.player.power + gained, 1.0)
            return
        power = self.player.power - self.drain() * dt / HOUR
        if power > 0:
            self.player.power = power
            return
        self.player.power = self.config.waking
        logger.info("%s  The player's power cell runs flat", self.clock)
        self.collapse()
