from starlette.applications import Starlette

from simile.sim.bus import EventBus
from simile.sim.clock import Clock, WallClock
from simile.sim.loop import TickLoop


class World:
    def __init__(self, clock: Clock | None = None, wall: WallClock | None = None) -> None:
        self.clock = clock or Clock()
        self.bus = EventBus()
        self.loop = TickLoop(self.clock, wall)


def world_of(app: Starlette) -> World:
    if not hasattr(app.state, "world"):
        app.state.world = World()
    return app.state.world
