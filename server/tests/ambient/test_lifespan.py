from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.ambient import Director, director_of
from simile.app import create_app
from simile.schema import Conversation
from simile.sim import STEP, Clock, ConversationStarted, FakeWallClock, World, world_of

MakePackage = Callable[[dict[str, str]], str]

START = datetime(2026, 1, 1, 10, tzinfo=UTC)


@pytest.fixture
def app(make_package: MakePackage) -> Starlette:
    lifespans = ("behaviour", "conversation", "llm", "memory", "protocol", "world")
    package = make_package(
        {
            f"{module}/lifespan.py": f"from simile.{module}.lifespan import lifespan\n"
            for module in lifespans
        }
        | {"ambient/lifespan.py": "from simile.ambient.lifespan import running\n"}
    )
    app = create_app(package)
    app.state.world = World(Clock(START), FakeWallClock())
    return app


def started(id: str) -> ConversationStarted:
    return ConversationStarted(Conversation(id=id, participants=["kofi", "tobias"], started=START))


def test_the_director_ticks_and_follows_the_bus_until_shutdown(app: Starlette) -> None:
    world = world_of(app)
    with TestClient(app):
        director = director_of(app)
        assert isinstance(director, Director)
        world.bus.publish(started("a"))
        for _ in range(round(director.config.look_every / STEP)):
            world.loop.tick()
        assert list(director.earshot.live) == ["a"]
        assert director.heard_at == world.clock.now

    world.bus.publish(started("b"))
    world.loop.tick()
    assert list(director.earshot.live) == ["a"]
    assert director.heard_at < world.clock.now
