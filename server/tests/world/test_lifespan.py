import json
from collections.abc import Callable

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.app import create_app
from simile.behaviour import GoalChosen
from simile.memory import memory_of
from simile.npc import load_npcs
from simile.persistence import player_of
from simile.protocol import hub_of
from simile.schema import PLAYER_ID, Bionic, Body, MapTile
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
        street = '{"x": 14, "y": 15, "map": "high_street"}'
        hub_of(app).receive(f'{{"type": "player_move", "position": {street}}}')
        outside = movement_of(app).position(PLAYER_ID)
        inside = '{"x": 10.5, "y": 2, "map": "coffee_shop_floor_0"}'
        hub_of(app).receive(f'{{"type": "player_move", "position": {inside}}}')

        assert outside == Point(14, 15, "high_street")
        assert movement_of(app).position(PLAYER_ID) == Point(10.5, 2, "coffee_shop_floor_0")


@pytest.mark.parametrize("onto", ['"map": "moon"', '"map": "village"', ""], ids=str)
def test_ignores_a_player_move_onto_an_unknown_map_or_none(
    make_package: MakePackage, caplog: pytest.LogCaptureFixture, onto: str
) -> None:
    app = create_app(make_package(WORLD_LIFESPAN))

    with TestClient(app):
        street = '{"x": 14, "y": 15, "map": "high_street"}'
        hub_of(app).receive(f'{{"type": "player_move", "position": {street}}}')
        nowhere = ", ".join(part for part in ('"x": 5, "y": 6', onto) if part)
        hub_of(app).receive(f'{{"type": "player_move", "position": {{{nowhere}}}}}')
        world_of(app).loop.tick()

        assert movement_of(app).position(PLAYER_ID) == Point(14, 15, "high_street")
    assert "Ignored a player_move onto an unknown map" in caplog.text


def send_moves(app: Starlette, *positions: tuple[float, float, str]) -> None:
    for x, y, map_id in positions:
        position = json.dumps({"x": x, "y": y, "map": map_id})
        hub_of(app).receive(f'{{"type": "player_move", "position": {position}}}')


def test_keeps_a_jump_and_a_fall_where_they_are(make_package: MakePackage) -> None:
    app = create_app(make_package(WORLD_LIFESPAN))

    with TestClient(app):
        movement = movement_of(app)
        send_moves(app, (47, 12, "lychee_lane"), (47.5, 12, "lychee_lane"))
        for x, y in [(48.6, 11.2), (49.9, 10.4), (51.2, 10.9), (52.3, 12.6), (53.1, 14.4)]:
            send_moves(app, (x, y, "lychee_lane"))
            world_of(app).loop.tick()
            assert movement.position(PLAYER_ID) == Point(x, y, "lychee_lane")
        send_moves(app, (20, 13.1, "high_street"))
        assert movement.position(PLAYER_ID) == Point(20, 13.1, "high_street")


@pytest.mark.parametrize("legs", [False, True], ids=["own legs", "hydraulic legs"])
def test_keeps_a_jump_a_row_higher_only_with_the_hydraulic_legs(
    make_package: MakePackage, legs: bool
) -> None:
    app = create_app(make_package(WORLD_LIFESPAN))

    with TestClient(app):
        if legs:
            player_of(app).body = Body(legs=Bionic.HYDRAULIC_LEGS)
        send_moves(app, (100, 15, "metro"), (100, 11.9, "metro"))

        assert (movement_of(app).position(PLAYER_ID) == Point(100, 11.9, "metro")) is legs


@pytest.mark.parametrize("datajack", [False, True], ids=["without", "with the datajack"])
def test_keeps_a_move_into_the_sewers_only_with_the_datajack(
    make_package: MakePackage, datajack: bool
) -> None:
    app = create_app(make_package(WORLD_LIFESPAN))

    with TestClient(app):
        if datajack:
            player_of(app).body = Body(vertebra=Bionic.DATAJACK)
        send_moves(app, (100, 15, "metro"), (3, 15, "sewers"))
        entered = movement_of(app).position(PLAYER_ID) == Point(3, 15, "sewers")
        send_moves(app, (100, 15, "metro"))

        assert entered is datajack
        assert movement_of(app).position(PLAYER_ID) == Point(100, 15, "metro")


@pytest.mark.parametrize(
    ("place", "where"),
    [
        ((20, 17, "high_street"), "in the ground"),
        ((20, 4, "high_street"), "high above any jump"),
        ((-3, 15, "high_street"), "off the map"),
        ((0, 1, "house_1_floor_0"), "in a wall"),
    ],
    ids=lambda value: value if isinstance(value, str) else "",
)
def test_ignores_a_player_move_to_where_nobody_could_be(
    make_package: MakePackage,
    caplog: pytest.LogCaptureFixture,
    place: tuple[float, float, str],
    where: str,
) -> None:
    app = create_app(make_package(WORLD_LIFESPAN))
    start = (3, 2, place[2]) if place[2].endswith("floor_0") else (20, 15, place[2])

    with TestClient(app):
        send_moves(app, start, place)

        assert movement_of(app).position(PLAYER_ID) == Point(*start), where
    assert "Ignored a player_move to where nobody could be" in caplog.text


def test_keeps_a_fall_from_the_clock_house_roof_but_not_a_sideways_jump_out_of_it(
    make_package: MakePackage, caplog: pytest.LogCaptureFixture
) -> None:
    app = create_app(make_package(WORLD_LIFESPAN))

    with TestClient(app):
        falling = [(56, 4, "rooftops"), (57.4, 4.6, "rooftops"), (58.2, 6.5, "rooftops")]
        send_moves(app, *falling, (44, 11, "rooftops"))

        assert movement_of(app).position(PLAYER_ID) == Point(58.2, 6.5, "rooftops")
    assert "Ignored a player_move to where nobody could be" in caplog.text


def test_stops_on_shutdown(make_package: MakePackage) -> None:
    app = create_app(make_package(WORLD_LIFESPAN))
    start = MapTile(map="lychee_lane", x=3, y=15)
    with TestClient(app):
        movement = movement_of(app)
        movement.place("mei", start)
        walk = movement.walk_to("mei", "coffee_shop")

    world_of(app).loop.tick()

    assert movement.position("mei") == Point(start.x, start.y, start.map)
    assert not walk.done


def test_residents_take_a_spot_for_the_goal_behaviour_publishes(make_package: MakePackage) -> None:
    app = create_app(make_package(WORLD_LIFESPAN))

    with TestClient(app):
        movement = movement_of(app)
        movement.place("mei", "square")
        world_of(app).bus.publish(GoalChosen("mei", "noodle_bar", "noodle_bar"))
        walk = movement.walk_to("mei", "noodle_bar")

    assert walk.destination is not None
    spot = MAPS[walk.destination.map].spot_at(walk.destination.x, walk.destination.y)
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


def test_the_snapshot_says_which_level_the_world_plays(
    make_package: MakePackage, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("simile.world.map.world_level", lambda: 3)
    app = create_app(make_package(WORLD_LIFESPAN))

    with TestClient(app):
        assert hub_of(app).snapshot().level == 3

    assert hub_of(app).snapshot().level == 0
