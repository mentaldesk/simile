import math
from datetime import UTC, datetime

import pytest

from simile.schema import VILLAGE_MAP, Facing, MapTile, Pose, Tile
from simile.sim import Clock, EntityMoved, FakeWallClock, World
from simile.world import Movement, Outcome, Walk
from simile.world.map import Spot, SpotKind, TownMap, load_maps
from simile.world.movement import inside
from simile.world.paths import Spot as PathSpot
from simile.world.spots import Purpose, choose, purpose_of, taste

MAPS = load_maps()
START = datetime(2026, 1, 1, 8, tzinfo=UTC)
GRID = {Facing.EAST, Facing.SOUTH, Facing.WEST, Facing.NORTH}
TABLE = (12, 7)
"""A café table, with a seat either side."""


class Village:
    def __init__(self, maps: dict[str, TownMap] = MAPS) -> None:
        self.world = World(Clock(START), FakeWallClock())
        self.movement = Movement(maps, self.world.bus)
        self.world.loop.register(self.movement)
        self.moves: list[EntityMoved] = []
        self.world.bus.subscribe(EntityMoved, self.moves.append)

    def finish(self, *walks: Walk) -> None:
        for _ in range(100_000):
            if all(walk.done for walk in walks):
                return
            self.world.loop.tick()
        raise AssertionError(walks)

    def go(self, entity: str, purpose: Purpose | None, target: str, start: str = "square") -> Walk:
        self.movement.place(entity, start)
        self.movement.intend(entity, purpose)
        walk = self.movement.walk_to(entity, target)
        self.finish(walk)
        return walk

    def spot(self, entity: str) -> Spot | None:
        return self.movement.on_spot(entity)


def spot_tile(spot: Spot) -> PathSpot:
    return PathSpot(spot.map, spot.x, spot.y)


def spots(map_id: str, kind: SpotKind | None = None) -> list[Spot]:
    return [spot for spot in MAPS[map_id].spots if kind is None or spot.kind is kind]


def test_every_spot_is_on_a_walkable_tile_of_its_own_facing_a_wall_or_a_thing() -> None:
    for town in MAPS.values():
        tiles = [(spot.x, spot.y) for spot in town.spots]
        assert len(tiles) == len(set(tiles)), town.id
        for spot in town.spots:
            assert spot.map == town.id
            assert town.walkable(spot.x, spot.y), spot
            assert spot.facing in GRID, spot
            assert math.hypot(spot.dx, spot.dy) < 1, spot


def test_every_spot_but_the_murals_is_in_a_place() -> None:
    walls = {(wall.stand.x, wall.stand.y) for wall in MAPS[VILLAGE_MAP].murals}
    for town in MAPS.values():
        for spot in town.spots:
            if town.id == VILLAGE_MAP and (spot.x, spot.y) in walls:
                assert spot.kind is SpotKind.VIEWING
                continue
            assert any(inside(location, spot_tile(spot)) for location in town.locations), spot


@pytest.mark.parametrize(
    ("map_id", "location", "kinds"),
    [
        ("coffee_shop", "coffee_shop", {SpotKind.SEAT, SpotKind.BAR}),
        ("noodle_bar", "noodle_bar", {SpotKind.SEAT}),
        ("maker_space", "maker_space", {SpotKind.DESK}),
        ("gallery", "gallery", {SpotKind.VIEWING, SpotKind.SEAT}),
        (VILLAGE_MAP, "park", {SpotKind.SEAT}),
        (VILLAGE_MAP, "square", {SpotKind.STANDING, SpotKind.SEAT, SpotKind.TERMINAL}),
        (VILLAGE_MAP, "terminal_2", {SpotKind.TERMINAL}),
    ],
)
def test_each_place_has_the_spots_its_furniture_offers(
    map_id: str, location: str, kinds: set[SpotKind]
) -> None:
    place = MAPS[map_id].location(location)
    assert {spot.kind for spot in spots(map_id) if inside(place, spot_tile(spot))} == kinds


def test_seats_face_their_table_and_sit_on_its_chairs() -> None:
    x, y = TABLE
    west, east = (MAPS["coffee_shop"].spot_at(x + dx, y) for dx in (-1, 1))
    assert west and east
    assert (west.kind, west.facing, west.pose) == (SpotKind.SEAT, Facing.EAST, Pose.SITTING)
    assert (east.kind, east.facing) == (SpotKind.SEAT, Facing.WEST)
    assert x - 1 < west.seat[0] < x < east.seat[0] < x + 1


def test_the_paintings_are_viewed_from_their_stand_tiles() -> None:
    gallery = MAPS["gallery"]
    viewing = {(spot.x, spot.y) for spot in spots("gallery", SpotKind.VIEWING)}
    stands = {(tile.x, tile.y) for item in gallery.interactables for tile in item.stand}
    assert viewing == stands
    assert {spot.pose for spot in spots("gallery", SpotKind.VIEWING)} == {Pose.LOOKING}


def test_only_the_stools_raise_a_sitter() -> None:
    raised = [spot for town in MAPS.values() for spot in town.spots if spot.dz]
    assert raised and all(spot.map == "noodle_bar" and spot.y == 5 for spot in raised)


@pytest.mark.parametrize(
    ("purpose", "target", "kinds"),
    [
        (Purpose.EAT, "noodle_bar", {SpotKind.SEAT}),
        (Purpose.DRINK, "coffee_shop", {SpotKind.BAR, SpotKind.SEAT}),
        (Purpose.READ, "terminal_1", {SpotKind.TERMINAL}),
        (Purpose.MAKE, "maker_space", {SpotKind.DESK}),
        (Purpose.LOOK, "gallery", {SpotKind.VIEWING}),
        (Purpose.RELAX, "park", {SpotKind.SEAT}),
        (Purpose.LINGER, "square", {SpotKind.STANDING, SpotKind.SEAT}),
    ],
)
def test_takes_a_free_spot_that_suits_what_they_are_there_for(
    purpose: Purpose, target: str, kinds: set[SpotKind]
) -> None:
    village = Village()

    walk = village.go("mei", purpose, target)

    spot = village.spot("mei")
    assert walk.outcome is Outcome.ARRIVED and spot is not None
    assert spot.kind in kinds
    assert walk.destination == MapTile(map=spot.map, x=spot.x, y=spot.y)
    last = village.moves[-1]
    assert (last.x, last.y, last.map) == (spot.x, spot.y, spot.map)
    assert (last.pose, last.facing) == (spot.pose, spot.facing)
    assert village.movement.posture("mei") == (spot.pose, spot.facing)


def test_a_full_place_falls_back_to_standing_nearby() -> None:
    village = Village()
    [terminal] = spots(VILLAGE_MAP, SpotKind.TERMINAL)[:1]
    village.movement.place("ada", Tile(x=terminal.x, y=terminal.y))

    walk = village.go("mei", Purpose.READ, "terminal_1")

    assert walk.outcome is Outcome.ARRIVED
    assert village.spot("mei") is None
    assert inside(village.movement.town.location("terminal_1"), village.movement.position("mei"))
    assert village.moves[-1].pose is Pose.STANDING


def test_standing_nearby_keeps_off_other_spots() -> None:
    village = Village()

    village.go("mei", None, "noodle_bar")

    entry = MAPS["noodle_bar"].location("noodle_bar").entry
    assert MAPS["noodle_bar"].spot_at(entry.x, entry.y) is not None
    assert village.spot("mei") is None
    assert village.movement.posture("mei")[0] is Pose.STANDING


def test_friends_sit_near_each_other() -> None:
    village = Village()
    x, y = TABLE
    village.movement.place("ada", MapTile(map="coffee_shop", x=x - 1, y=y))
    village.movement.affinity = lambda a, b: 1.0 if {a, b} == {"ada", "mei"} else 0.0

    village.go("mei", Purpose.EAT, "coffee_shop")

    assert village.movement.position("mei") == (x + 1, y)


def test_people_sit_away_from_someone_they_dislike() -> None:
    village = Village()
    x, y = TABLE
    village.movement.place("ada", MapTile(map="coffee_shop", x=x - 1, y=y))
    village.movement.affinity = lambda a, b: -1.0

    village.go("mei", Purpose.EAT, "coffee_shop")

    here = village.movement.position("mei")
    assert math.dist(here, (x - 1, y)) >= 3


def test_someone_already_on_a_suitable_spot_stays_there() -> None:
    village = Village()
    x, y = TABLE
    village.movement.place("mei", MapTile(map="coffee_shop", x=x + 1, y=y))
    village.movement.intend("mei", Purpose.DRINK)
    village.moves.clear()

    walk = village.movement.walk_to("mei", "coffee_shop")

    assert walk.outcome is Outcome.ARRIVED and walk.distance == 0
    assert village.movement.position("mei") == (x + 1, y)


def test_walking_faces_each_step_and_stopping_off_a_spot_keeps_the_last_facing() -> None:
    village = Village()
    village.movement.place("mei", Tile(x=24, y=20))
    village.moves.clear()

    village.finish(village.movement.walk_to("mei", Tile(x=22, y=20)))

    assert [(m.x, m.pose, m.facing) for m in village.moves] == [
        (23, Pose.WALKING, Facing.WEST),
        (22, Pose.STANDING, Facing.WEST),
    ]


def test_stopping_mid_walk_on_a_spot_takes_its_pose() -> None:
    village = Village()
    [bench, _] = [s for s in spots(VILLAGE_MAP, SpotKind.SEAT) if s.y == 19][:2]
    village.movement.place("mei", Tile(x=bench.x - 1, y=bench.y))
    walk = village.movement.walk_to("mei", Tile(x=bench.x + 3, y=bench.y))

    def stop_on_the_bench(moved: EntityMoved) -> None:
        if (moved.x, moved.y) == (bench.x, bench.y) and not walk.done:
            village.movement.stop("mei")

    village.world.bus.subscribe(EntityMoved, stop_on_the_bench)
    village.finish(walk)

    assert village.movement.posture("mei") == (Pose.SITTING, bench.facing)


def test_a_muralist_works_on_the_spot_others_look_from() -> None:
    village = Village()
    wall = MAPS[VILLAGE_MAP].murals[0]
    stand = MapTile(map=VILLAGE_MAP, x=wall.stand.x, y=wall.stand.y)

    for entity, purpose, pose in (
        ("kofi", Purpose.MAKE, Pose.WORKING),
        ("mei", None, Pose.LOOKING),
    ):
        village.movement.place(entity, "square")
        village.movement.intend(entity, purpose)
        village.finish(village.movement.walk_to(entity, stand))
        assert village.movement.posture(entity)[0] is pose
        village.movement.place(entity, "square")


def test_placing_someone_on_a_spot_seats_them() -> None:
    village = Village()
    x, y = TABLE

    village.movement.place("mei", MapTile(map="coffee_shop", x=x - 1, y=y))

    assert (village.moves[-1].pose, village.moves[-1].facing) == (Pose.SITTING, Facing.EAST)


@pytest.mark.parametrize(
    ("activity", "target", "purpose"),
    [
        ("coffee_shop", "coffee_shop", Purpose.DRINK),
        ("noodle_bar", "noodle_bar", Purpose.EAT),
        ("news", "terminal_2", Purpose.READ),
        ("maker_space", "maker_space", Purpose.MAKE),
        ("create", "coffee_shop", Purpose.MAKE),
        ("gallery", "gallery", Purpose.LOOK),
        ("park", "park", Purpose.RELAX),
        ("square", "square", Purpose.LINGER),
        ("work", "maker_space", Purpose.MAKE),
        ("work", "gallery", Purpose.LOOK),
        ("work", "coffee_shop", None),
        ("work", "noodle_bar", None),
        ("work", "house_1", None),
        ("home", "house_1", None),
        ("seek", "ada", None),
        ("talk", "ada", None),
    ],
)
def test_what_each_goal_is_there_for(activity: str, target: str, purpose: Purpose | None) -> None:
    assert purpose_of(activity, target) is purpose


def test_each_resident_has_their_own_favourites() -> None:
    seats = spots("coffee_shop", SpotKind.SEAT)
    kinds = {SpotKind.SEAT: 0.0}

    favourites = {
        entity: choose(entity, seats, kinds, {}, None, lambda a, b: 0.0)
        for entity in ("ada", "mei", "kofi", "ingrid", "tobias")
    }

    assert len(set(favourites.values())) > 1
    assert all(0 <= taste(entity, seats[0]) <= 1 for entity in favourites)
    assert favourites["ada"] == choose("ada", seats, kinds, {}, None, lambda a, b: 0.0)
