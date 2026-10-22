from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.app import create_app
from simile.behaviour import behaviour_of
from simile.conversation import conversations_of
from simile.memory import memory_of
from simile.persistence import player_of
from simile.schema import PLAYER_ID, Bionic, Body, MemoryKind
from simile.sim import Clock, World
from simile.social.sightings import sightings_of
from simile.world.movement import Point

MakePackage = Callable[[dict[str, str]], str]

START = datetime(2026, 1, 1, 10, tzinfo=UTC)


@pytest.fixture
def app(make_package: MakePackage) -> Starlette:
    modules = ("behaviour", "conversation", "llm", "memory", "protocol", "social", "world")
    package = make_package(
        {
            f"{module}/lifespan.py": f"from simile.{module}.lifespan import lifespan\n"
            for module in modules
        }
    )
    app = create_app(package)
    app.state.world = World(Clock(START))
    return app


def test_plugs_unease_into_b1_and_what_they_see_into_b2_until_shutdown(app: Starlette) -> None:
    with TestClient(app) as client:
        behaviour, sightings = behaviour_of(app), sightings_of(app)
        assert behaviour.hooks.unease == sightings.unease
        assert conversations_of(app).looks("tobias") is None

        player_of(app).body = Body(left_eye=Bionic.INFRARED_EYE)
        here = behaviour.movement.position("tobias")
        behaviour.movement.track(PLAYER_ID, Point(here.x + 1, here.y, here.map))
        client.portal.call(sightings.look)

        assert (conversations_of(app).looks("tobias") or "").startswith("Visitor has an infrared")
        assert behaviour.unease("tobias") == 1
        [seen] = memory_of(app).recall("tobias", START, kind=MemoryKind.OBSERVATION)
        assert seen.about == [PLAYER_ID]

    assert behaviour.hooks.unease != sightings.unease
