import threading
from collections.abc import Callable, Sequence

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.app import create_app
from simile.sim import FakeWallClock, RealWallClock, World, world_of

MakePackage = Callable[[dict[str, str]], str]
MakeVillage = Callable[..., str]

SLOW_LIFESPAN = (
    "import asyncio\n"
    "from contextlib import asynccontextmanager\n"
    "@asynccontextmanager\n"
    "async def lifespan(app):\n"
    "    for _ in range(50):\n"
    "        await asyncio.sleep(0)\n"
    "    yield\n"
    "    for _ in range(50):\n"
    "        await asyncio.sleep(0)\n"
)

READY_LIFESPAN = (
    "from contextlib import asynccontextmanager\n"
    "from simile.sim import world_of\n"
    "@asynccontextmanager\n"
    "async def lifespan(app):\n"
    "    world_of(app).ready = True\n"
    "    yield\n"
    "    world_of(app).ready = False\n"
)


def hooks_source(module: str, hooks: Sequence[str]) -> str:
    source = "from contextlib import asynccontextmanager\n"
    for hook in hooks:
        source += (
            "@asynccontextmanager\n"
            f"async def {hook}(app):\n"
            "    app.state.events = getattr(app.state, 'events', [])\n"
            f"    app.state.events.append('{module} {hook} up')\n"
            "    yield\n"
            f"    app.state.events.append('{module} {hook} down')\n"
        )
    return source


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


class ReadinessRecorder:
    def __init__(self) -> None:
        self.ticked = threading.Event()
        self.ready: list[bool] = []

    def attach(self, world: World) -> "ReadinessRecorder":
        self.world = world
        return self

    def tick(self, dt: float) -> None:
        self.ready.append(getattr(self.world, "ready", False))
        self.ticked.set()


def test_world_of_creates_one_world_at_1x() -> None:
    app = Starlette()

    world = world_of(app)

    assert world_of(app) is world
    assert world.clock.speed == 1
    assert isinstance(world.loop.wall, RealWallClock)


def test_running_hooks_enter_after_every_lifespan_and_exit_before_any(
    make_package: MakePackage,
) -> None:
    package = make_package(
        {
            "alpha/lifespan.py": hooks_source("alpha", ["lifespan", "running"]),
            "beta/lifespan.py": hooks_source("beta", ["running"]),
            "gamma/lifespan.py": hooks_source("gamma", ["lifespan"]),
        }
    )
    app = create_app(package)

    with TestClient(app):
        assert app.state.events == [
            "alpha lifespan up",
            "gamma lifespan up",
            "alpha running up",
            "beta running up",
        ]

    assert app.state.events[4:] == [
        "beta running down",
        "alpha running down",
        "gamma lifespan down",
        "alpha lifespan down",
    ]


def test_serve_ticks_systems_registered_before_and_after_sim(make_village: MakeVillage) -> None:
    alpha, zeta = Ticked(), Ticked()
    app = create_app(make_village({"alpha": [lambda world: alpha], "zeta": [lambda world: zeta]}))
    app.state.world = World(wall=FakeWallClock())

    with TestClient(app):
        assert alpha.event.wait(5)
        assert zeta.event.wait(5)


def test_serve_only_ticks_while_every_module_is_up(make_village: MakeVillage) -> None:
    recorder = ReadinessRecorder()
    package = make_village(
        {"behaviour": [recorder.attach]},
        {"voice/lifespan.py": SLOW_LIFESPAN, "world/lifespan.py": READY_LIFESPAN},
    )
    app = create_app(package)
    app.state.world = World(wall=FakeWallClock())

    with TestClient(app):
        assert recorder.ticked.wait(5)

    assert all(recorder.ready)


def test_a_crashed_loop_is_logged_and_shuts_down_cleanly(
    make_village: MakeVillage, caplog: pytest.LogCaptureFixture
) -> None:
    broken = Broken()
    app = create_app(make_village({"town": [lambda world: broken]}))
    app.state.world = World(wall=FakeWallClock())

    with TestClient(app):
        assert broken.raised.wait(5)

    assert "The tick loop stopped" in caplog.text
    assert "boom" in caplog.text
