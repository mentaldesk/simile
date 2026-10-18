from collections.abc import Callable

import pytest
from starlette.testclient import TestClient

from simile.app import create_app
from simile.protocol import hub_of
from simile.schema import PLAYER_ID, VILLAGE_MAP, Tile
from simile.sim import world_of
from simile.world import Point, movement_of

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
        outside = movement_of(app).position(PLAYER_ID)
        inside = '{"x": 10, "y": 12, "map": "coffee_shop"}'
        hub_of(app).receive(f'{{"type": "player_move", "position": {inside}}}')

        assert outside == Point(14, 12.5, VILLAGE_MAP)
        assert movement_of(app).position(PLAYER_ID) == Point(10, 12, "coffee_shop")


def test_ignores_a_player_move_onto_an_unknown_map(
    make_package: MakePackage, caplog: pytest.LogCaptureFixture
) -> None:
    app = create_app(make_package(WORLD_LIFESPAN))

    with TestClient(app):
        hub_of(app).receive('{"type": "player_move", "position": {"x": 14, "y": 12.5}}')
        hub_of(app).receive('{"type": "player_move", "position": {"x": 5, "y": 6, "map": "moon"}}')
        world_of(app).loop.tick()

        assert movement_of(app).position(PLAYER_ID) == Point(14, 12.5, VILLAGE_MAP)
    assert "Ignored a player_move onto an unknown map" in caplog.text


def test_stops_on_shutdown(make_package: MakePackage) -> None:
    app = create_app(make_package(WORLD_LIFESPAN))
    with TestClient(app):
        movement = movement_of(app)
        movement.place("mei", Tile(x=3, y=11))
        walk = movement.walk_to("mei", "coffee_shop")

    world_of(app).loop.tick()

    assert movement.position("mei") == (3, 11)
    assert not walk.done
