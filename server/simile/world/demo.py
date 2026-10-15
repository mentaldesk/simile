import logging
from datetime import datetime
from itertools import cycle

from simile.sim import Clock
from simile.world.movement import Movement, Walk

logger = logging.getLogger(__name__)

DEMO_ENV = "SIMILE_DEMO_WALK"
WALKER = "mei"
HOME = "house_1"
COFFEE_SHOP = "coffee_shop"
REST = 30.0


class WalkDemo:
    """Mei walks from home to the coffee shop and back, resting at each end."""

    def __init__(self, movement: Movement, clock: Clock) -> None:
        self.movement = movement
        self.clock = clock
        self.trips = cycle([(HOME, COFFEE_SHOP), (COFFEE_SHOP, HOME)])
        self.walking = False
        self.resting = 0.0
        movement.place(WALKER, HOME)

    def tick(self, dt: float) -> None:
        if self.walking:
            return
        self.resting -= dt
        if self.resting > 0:
            return
        start, end = next(self.trips)
        began = self.clock.now
        self.walking = True
        walk = self.movement.walk_to(WALKER, end)
        walk.add_done_callback(lambda walk: self.arrived(walk, start, began))

    def arrived(self, walk: Walk, start: str, began: datetime) -> None:
        seconds = (self.clock.now - began).total_seconds()
        logger.info(
            f"{self.clock}  {WALKER} walked from {start} to {walk.target} ({walk.outcome}): "
            f"{walk.distance:.1f} tiles in {seconds:.1f} s, "
            f"{walk.distance / max(seconds, 1e-9):.2f} tiles/s"
        )
        self.walking = False
        self.resting = REST
