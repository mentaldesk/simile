import threading
from collections.abc import Callable

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.app import create_app
from simile.sim import FakeWallClock, RealWallClock, World, world_of

MakeVillage = Callable[..., str]


class Ticked:
    def __init__(self) -> None:
        self.event = threading.Event()

    def tick(self, dt: float) -> None:
        self.event.set()


class Broken:
    def __init__(self) -> None:
        self.raised = threading.Event()

    def tick(self, dt: float) -> None:
        self.raised.set()
        raise RuntimeError("boom")


def test_world_of_creates_one_world_at_1x() -> None:
    app = Starlette()

    world = world_of(app)

    assert world_of(app) is world
    assert world.clock.speed == 1
    assert isinstance(world.loop.wall, RealWallClock)


def test_serve_ticks_systems_registered_before_and_after_sim(make_village: MakeVillage) -> None:
    alpha, zeta = Ticked(), Ticked()
    app = create_app(make_village(alpha=[lambda world: alpha], zeta=[lambda world: zeta]))
    app.state.world = World(wall=FakeWallClock())

    with TestClient(app):
        assert alpha.event.wait(5)
        assert zeta.event.wait(5)


def test_a_crashed_loop_is_logged_and_shuts_down_cleanly(
    make_village: MakeVillage, caplog: pytest.LogCaptureFixture
) -> None:
    broken = Broken()
    app = create_app(make_village(town=[lambda world: broken]))
    app.state.world = World(wall=FakeWallClock())

    with TestClient(app):
        assert broken.raised.wait(5)

    assert "The tick loop stopped" in caplog.text
    assert "boom" in caplog.text
