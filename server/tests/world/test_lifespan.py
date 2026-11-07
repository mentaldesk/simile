import json
from collections.abc import Callable

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.app import create_app
from simile.memory import memory_of
from simile.npc import load_npcs
from simile.persistence import player_of
from simile.protocol import hub_of
from simile.schema import PLAYER_ID, Bionic, Body, MapTile, Player
from simile.sim import world_of
from simile.social import meet
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


def restore_player(app: Starlette, player: Player) -> None:
    """Their state back in place, through JSON as a reload has it."""
    loaded = Player.model_validate_json(player.model_dump_json())
    for field in Player.model_fields:
        setattr(player_of(app), field, getattr(loaded, field))


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


@pytest.mark.parametrize("feet", [False, True], ids=["own feet", "spring feet"])
def test_keeps_a_jump_a_row_higher_only_with_the_spring_feet(
    make_package: MakePackage, feet: bool
) -> None:
    app = create_app(make_package(WORLD_LIFESPAN))

    with TestClient(app):
        if feet:
            player_of(app).body = Body(feet=Bionic.SPRING_FEET)
        send_moves(app, (100, 15, "metro"), (100, 11.9, "metro"))

        assert (movement_of(app).position(PLAYER_ID) == Point(100, 11.9, "metro")) is feet


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


def test_a_new_body_rides_the_lift_once_a_body_has_had_the_datajack_across_a_save(
    make_package: MakePackage,
) -> None:
    app = create_app(make_package(WORLD_LIFESPAN))

    with TestClient(app):
        player = player_of(app)
        player.body = Body(vertebra=Bionic.DATAJACK)
        player.body = Body()
        restore_player(app, player)
        send_moves(app, (100, 15, "metro"), (3, 15, "sewers"))

        assert Bionic.DATAJACK not in player_of(app).body.bionics
        assert movement_of(app).position(PLAYER_ID) == Point(3, 15, "sewers")


def test_a_body_that_never_opened_the_lift_stays_out_across_a_save(
    make_package: MakePackage,
) -> None:
    app = create_app(make_package(WORLD_LIFESPAN))

    with TestClient(app):
        player = player_of(app)
        player.body = Body(legs=Bionic.BIONIC_LEGS)
        player.searched = ["metro_fridge"]
        restore_player(app, player)
        send_moves(app, (100, 15, "metro"), (3, 15, "sewers"))

        assert movement_of(app).position(PLAYER_ID) == Point(100, 15, "metro")


def test_a_save_from_before_the_lift_stayed_open_opens_it_for_a_body_with_no_datajack(
    make_package: MakePackage,
) -> None:
    app = create_app(make_package(WORLD_LIFESPAN))
    down = {"map": "sewers", "x": 3, "y": 15}
    corpse = {
        "id": "corpse_1",
        "owner": "player",
        "at": down,
        "money": 0,
        "items": [],
        "bionics": [],
    }

    with TestClient(app):
        saved = Player.model_validate_json(json.dumps({"corpses": [corpse]}))
        restore_player(app, saved)
        send_moves(app, (100, 15, "metro"), (3, 15, "sewers"))

        assert movement_of(app).position(PLAYER_ID) == Point(3, 15, "sewers")


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
