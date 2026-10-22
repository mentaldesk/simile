"""The player's jump: the client plays it from `content/street/jump.json`, which `simile street`
writes from here, and the server checks the player's positions and paths by it."""

import json
import math
from dataclasses import asdict, dataclass
from typing import Any

RUN_SPEED = 5.2
"""Tiles a second, running: the client's `PLAYER_SPEED` times `RUN_PACE`, four times
`simile.world.map.WALKING_SPEED`."""
JUMP_FILE = "jump.json"


@dataclass(frozen=True)
class Jump:
    rise: float = 2.3
    """Tiles the feet rise with Space held."""
    rise_seconds: float = 0.38
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
    cells: int = 4
    """Along a row from a standing cell to the one a run jump lands on, for paths."""
    rows: int = 2
    """Up from a standing cell to the one a jump lands on, for paths."""
    frame_seconds: float = 0.1
    """The longest step the client takes, its `MAX_FRAME_SECONDS`: a jump can run on that long
    past where it would have taken off."""

    @property
    def gravity(self) -> float:
        """Tiles a second a second, rising with Space held."""
        return 2 * self.rise / self.rise_seconds**2

    @property
    def reach(self) -> float:
        """Tiles along the row from the middle of the cell the farthest jump takes off from to
        the farthest it gets before it's back down to where it took off: a run jump with Space
        held, as late as coyote time allows, at the client's longest step."""
        down = math.sqrt(2 * self.rise / (self.gravity * self.fall_gravity))
        airborne = self.frame_seconds + self.coyote_seconds + self.rise_seconds + down
        return 0.5 + self.foot + RUN_SPEED * airborne


JUMP = Jump()


def jump_table(jump: Jump = JUMP) -> dict[str, Any]:
    return {**asdict(jump), "reach": round(jump.reach, 3)}


def dumps(jump: Jump = JUMP) -> str:
    return json.dumps(jump_table(jump), indent=2) + "\n"
