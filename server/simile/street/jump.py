"""The player's jump on each grade of legs, which `simile street` writes to jump.json."""

import json
import math
from dataclasses import asdict, dataclass, replace
from typing import Any

from simile.schema import Bionic, Body

RUN_SPEED = 5.2
"""Tiles a second running on their own legs: the client's `PLAYER_SPEED` times `RUN_PACE`."""
JUMP_FILE = "jump.json"


@dataclass(frozen=True)
class Jump:
    rise: float = 2.3
    """Tiles the feet rise with Space held."""
    rise_seconds: float = 0.38
    run: float = RUN_SPEED
    """Tiles a second running, and flying along in a run jump."""
    fall_gravity: float = 1.3
    """Times the gravity rising with Space held, falling or once Space is let go."""
    cut: float = 0.45
    """Of its speed up a jump keeps when Space is let go on the way up."""
    coyote_seconds: float = 0.1
    """After walking off a ledge, Space still jumps for this long."""
    buffer_seconds: float = 0.12
    """Space pressed this long before landing jumps again on landing."""
    foot: float = 0.25
    """Half the width of the feet, which can stand on a ledge's edge, and of the body."""
    body: float = 1.7
    """From the feet to the top of the head."""
    frame_seconds: float = 0.1
    """The client's longest step, `MAX_FRAME_SECONDS`, which a jump can overrun its take-off by."""

    @property
    def gravity(self) -> float:
        """Tiles a second a second, rising with Space held."""
        return 2 * self.rise / self.rise_seconds**2

    def airtime(self, rise: float | None = None) -> float:
        """Seconds a jump is in the air back down to where it took off, rising at most `rise`."""
        up = self.rise if rise is None else min(rise, self.rise)
        return math.sqrt(2 * up / self.gravity) * (1 + 1 / math.sqrt(self.fall_gravity))

    @property
    def rows(self) -> int:
        """Up from a standing cell to the one a jump lands on, for paths."""
        return math.floor(self.rise)

    def along(self, rise: float | None = None) -> int:
        """Cells along a row a run jump rising at most `rise` lands from its middle, for paths."""
        return math.floor(0.5 + self.foot + self.run * self.airtime(rise))

    @property
    def cells(self) -> int:
        return self.along()

    @property
    def reach(self) -> float:
        """Tiles along the row the farthest jump gets from the middle of its take-off cell."""
        airborne = self.frame_seconds + self.coyote_seconds + self.airtime()
        return 0.5 + self.foot + self.run * airborne


JUMP = Jump()
"""The player's own legs."""


def legs(rise: float = JUMP.rise, run: float = RUN_SPEED) -> Jump:
    """A grade of legs' jump, rising `rise` tiles under the same gravity and running at `run`."""
    return replace(
        JUMP, rise=rise, rise_seconds=JUMP.rise_seconds * math.sqrt(rise / JUMP.rise), run=run
    )


GRADES: dict[Bionic, Jump] = {
    Bionic.HYDRAULIC_LEGS: legs(rise=4.3),
    Bionic.SPRING_LEGS: legs(rise=6.3),
    Bionic.SPRINT_LEGS: legs(run=7.8),
    Bionic.BLADE_LEGS: legs(run=10.4),
    Bionic.PREMIUM_LEGS: legs(rise=6.3, run=10.4),
}
"""Each grade of legs' jump: spring legs rise higher, sprint legs run faster, premium do both."""
OWN_JUMP = "jump"
NEEDS: dict[str, Jump] = {OWN_JUMP: JUMP, **{grade.value: jump for grade, jump in GRADES.items()}}
"""What reaching a place takes, on one scale for every map, as a pickup's `needs` records it."""


def jump_of(body: Body) -> Jump:
    return GRADES.get(body.legs, JUMP) if isinstance(body.legs, Bionic) else JUMP


def meets(jump: Jump, needs: str) -> bool:
    """Whether `jump` rises as high and runs as fast as a place that `needs` it takes."""
    needed = NEEDS[needs]
    return jump.rise >= needed.rise and jump.run >= needed.run


def _table(jump: Jump) -> dict[str, Any]:
    return {**asdict(jump), "rows": jump.rows, "cells": jump.cells, "reach": round(jump.reach, 3)}


def jump_table() -> dict[str, Any]:
    """The player's own jump, and under `legs` what each grade of legs changes of it."""
    own = _table(JUMP)
    changed = {
        grade.value: {key: value for key, value in _table(jump).items() if value != own[key]}
        for grade, jump in GRADES.items()
    }
    return {**own, "legs": changed}


def dumps() -> str:
    return json.dumps(jump_table(), indent=2) + "\n"
