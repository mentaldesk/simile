from collections.abc import Callable

import pytest
from starlette.testclient import TestClient

from simile.app import create_app
from simile.behaviour import GoalChosen
from simile.memory import memory_of
from simile.npc import load_npcs
from simile.protocol import hub_of
from simile.schema import PLAYER_ID, VILLAGE_MAP, Tile
from simile.sim import world_of
from simile.social import meet
from simile.world import Point, movement_of
from simile.world.map import SpotKind, load_maps

MAPS = load_maps()

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


def test_residents_take_a_spot_for_the_goal_behaviour_publishes(make_package: MakePackage) -> None:
    app = create_app(make_package(WORLD_LIFESPAN))

    with TestClient(app):
        movement = movement_of(app)
        movement.place("mei", "square")
        world_of(app).bus.publish(GoalChosen("mei", "noodle_bar", "noodle_bar"))
        walk = movement.walk_to("mei", "noodle_bar")

    assert walk.destination is not None
    spot = MAPS["noodle_bar"].spot_at(walk.destination.x, walk.destination.y)
    assert spot is not None and spot.kind is SpotKind.SEAT


def test_spots_go_by_behaviours_affinity_once_it_runs(make_package: MakePackage) -> None:
    lifespans = {
        f"{module}/lifespan.py": f"from simile.{module}.lifespan import lifespan\n"
        for module in ("behaviour", "memory", "world")
    }
    without = create_app(make_package(WORLD_LIFESPAN))
    with TestClient(without):
        assert movement_of(without).affinity("kofi", "ingrid") == 0

    app = create_app(make_package(lifespans))
    with TestClient(app):
        a, b, c = load_npcs()[:3]
        friend = meet(a, b.id).model_copy(
            update={"like": 1.0, "trust": 1.0, "respect": 1.0, "familiarity": 1.0}
        )
        memory_of(app).add(friend)
        affinity = movement_of(app).affinity

        assert affinity(a.id, b.id) > max(affinity(a.id, c.id), 0)
