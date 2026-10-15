import asyncio
import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from starlette.testclient import TestClient

from simile.app import create_app
from simile.protocol import hub_of
from simile.schema import PLAYER_ID, Tile
from simile.sim import Clock, FakeWallClock, World, world_of
from simile.sim.headless import run_headless
from simile.world import movement_of
from simile.world.demo import DEMO_ENV

MakePackage = Callable[[dict[str, str]], str]

WORLD_LIFESPAN = {"world/lifespan.py": "from simile.world.lifespan import lifespan\n"}


def test_moves_entities_on_the_tick_loop(make_package: MakePackage) -> None:
    app = create_app(make_package(WORLD_LIFESPAN))

    with TestClient(app):
        movement = movement_of(app)
        movement.place("mei", "house_1")
        movement.walk_to("mei", "coffee_shop")
        world_of(app).loop.tick()

        assert movement.position("mei") != (3, 11)


def test_tracks_the_player_from_player_move(make_package: MakePackage) -> None:
    app = create_app(make_package(WORLD_LIFESPAN))

    with TestClient(app):
        hub_of(app).receive('{"type": "player_move", "position": {"x": 14, "y": 12.5}}')

        assert movement_of(app).position(PLAYER_ID) == (14, 12.5)


def test_stops_on_shutdown(make_package: MakePackage) -> None:
    app = create_app(make_package(WORLD_LIFESPAN))
    with TestClient(app):
        movement = movement_of(app)
        movement.place("mei", Tile(x=3, y=11))
        walk = movement.walk_to("mei", "coffee_shop")

    world_of(app).loop.tick()

    assert movement.position("mei") == (3, 11)
    assert not walk.done


def walk_demo(package: str) -> None:
    world = World(Clock(datetime(2026, 1, 1, 8, tzinfo=UTC), speed=10), FakeWallClock())
    asyncio.run(run_headless(world, timedelta(minutes=1), package))


def test_demo_walks_mei_from_home_to_the_coffee_shop(
    make_package: MakePackage, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv(DEMO_ENV, "1")
    caplog.set_level(logging.INFO, logger="simile")

    walk_demo(make_package(WORLD_LIFESPAN))

    assert "EntityMoved(entity='mei', x=3.0, y=11.0)" in caplog.messages[0]
    assert "EntityMoved(entity='mei', x=31.0, y=11.0)" in caplog.text
    arrival = next(m for m in caplog.messages if "walked from house_1 to coffee_shop" in m)
    speed = re.search(r"arrived\): [\d.]+ tiles in [\d.]+ s, ([\d.]+) tiles/s", arrival)
    assert speed and float(speed[1]) == pytest.approx(1.3, abs=0.01)


def test_no_demo_without_the_environment_variable(
    make_package: MakePackage, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv(DEMO_ENV, raising=False)
    caplog.set_level(logging.INFO, logger="simile")

    walk_demo(make_package(WORLD_LIFESPAN))

    assert "mei" not in caplog.text
