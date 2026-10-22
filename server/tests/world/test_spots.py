import math
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from simile.schema import Facing, MapTile, Pose
from simile.sim import Clock, EntityMoved, FakeWallClock, World
from simile.world import Movement, Outcome, Walk
from simile.world.map import Spot, SpotKind, TownMap, load_maps, with_every_location
from simile.world.movement import inside
from simile.world.paths import Spot as PathSpot
from simile.world.spots import Purpose, choose, purpose_of, taste

MAPS = load_maps()
TOWN = with_every_location(MAPS)
START = datetime(2026, 1, 1, 8, tzinfo=UTC)
GRID = {Facing.EAST, Facing.SOUTH, Facing.WEST, Facing.NORTH}
UPSTAIRS = "coffee_shop_floor_1"
TABLE = (1, 2)
"""The west seat at a café table upstairs, facing the east one across it."""
SQUARE = "high_street"


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


def everywhere(kind: SpotKind | None = None) -> list[Spot]:
    return [spot for map_id in MAPS for spot in spots(map_id, kind)]


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
    walls = {(wall.map, wall.stand.x, wall.stand.y) for wall in TOWN.murals}
    for spot in everywhere():
        if (spot.map, spot.x, spot.y) in walls:
            assert spot.kind is SpotKind.VIEWING
            continue
        assert any(inside(location, spot_tile(spot)) for location in TOWN.locations), spot


@pytest.mark.parametrize(
    ("location", "kinds"),
    [
        ("coffee_shop", {SpotKind.SEAT, SpotKind.BAR}),
        ("noodle_bar", {SpotKind.SEAT}),
        ("maker_space", {SpotKind.DESK}),
        ("gallery", {SpotKind.VIEWING, SpotKind.SEAT}),
        ("park", {SpotKind.SEAT}),
        ("square", {SpotKind.STANDING, SpotKind.SEAT, SpotKind.TERMINAL}),
        ("terminal_2", {SpotKind.TERMINAL}),
    ],
)
def test_each_place_has_the_spots_its_furniture_offers(location: str, kinds: set[SpotKind]) -> None:
    place = TOWN.location(location)
    assert {spot.kind for spot in everywhere() if inside(place, spot_tile(spot))} == kinds


def test_seats_face_each_other_across_their_table() -> None:
    x, y = TABLE
    west, east = (MAPS[UPSTAIRS].spot_at(x + dx, y) for dx in (0, 1))
    assert west and east
    assert (west.kind, west.facing, west.pose) == (SpotKind.SEAT, Facing.EAST, Pose.SITTING)
    assert (east.kind, east.facing) == (SpotKind.SEAT, Facing.WEST)
    assert west.seat == (x, y) and east.seat == (x + 1, y)


def test_the_paintings_are_viewed_from_their_stand_tiles() -> None:
    floors = [town for town in MAPS.values() if town.building == "gallery"]
    viewing = {
        (spot.map, spot.x, spot.y)
        for town in floors
        for spot in town.spots
        if spot.kind is SpotKind.VIEWING
    }
    stands = {
        (item.map, tile.x, tile.y)
        for town in floors
        for item in town.interactables
        for tile in item.stand
    }
    assert viewing == stands
    assert {spot.pose for spot in everywhere(SpotKind.VIEWING)} == {Pose.LOOKING}


def test_only_the_stools_raise_a_sitter() -> None:
    raised = [spot for spot in everywhere() if spot.dz]
    assert {spot.map for spot in raised} == {"noodle_bar_floor_0", "coffee_shop_floor_0"}
    assert {spot.pose for spot in raised} == {Pose.SITTING}
    assert {spot.facing for spot in raised} == {Facing.EAST, Facing.WEST}


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
    [terminal] = [spot for spot in spots(SQUARE, SpotKind.TERMINAL)]
    village.movement.place("ada", MapTile(map=SQUARE, x=terminal.x, y=terminal.y))

    walk = village.go("mei", Purpose.READ, "terminal_1")

    assert walk.outcome is Outcome.ARRIVED
    assert village.spot("mei") is None
    here = village.movement.position("mei")
    assert inside(TOWN.location("square"), here) and abs(here.x - terminal.x) < 5
    assert village.moves[-1].pose is Pose.STANDING


def test_standing_nearby_keeps_off_other_spots() -> None:
    village = Village()
    noodles = TOWN.location("noodle_bar")
    village.movement.place("ada", MapTile(map=noodles.map, **noodles.entry.model_dump()))

    village.go("mei", None, "noodle_bar")

    assert village.spot("mei") is None
    assert inside(noodles, village.movement.position("mei"))
    assert village.movement.posture("mei")[0] is Pose.STANDING


def test_friends_sit_near_each_other() -> None:
    village = Village()
    x, y = TABLE
    village.movement.place("ada", MapTile(map=UPSTAIRS, x=x, y=y))
    village.movement.affinity = lambda a, b: 1.0 if {a, b} == {"ada", "mei"} else 0.0

    village.go("mei", Purpose.EAT, "coffee_shop")

    assert village.movement.position("mei") == (x + 1, y)


def test_people_sit_away_from_someone_they_dislike() -> None:
    village = Village()
    x, y = TABLE
    village.movement.place("ada", MapTile(map=UPSTAIRS, x=x, y=y))
    village.movement.affinity = lambda a, b: -1.0

    village.go("mei", Purpose.EAT, "coffee_shop")

    here = village.movement.position("mei")
    assert here.map == UPSTAIRS and abs(here.x - x) >= 3


def test_someone_already_on_a_suitable_spot_stays_there() -> None:
    village = Village()
    x, y = TABLE
    village.movement.place("mei", MapTile(map=UPSTAIRS, x=x + 1, y=y))
    village.movement.intend("mei", Purpose.DRINK)
    village.moves.clear()

    walk = village.movement.walk_to("mei", "coffee_shop")

    assert walk.outcome is Outcome.ARRIVED and walk.distance == 0
    assert village.movement.position("mei") == (x + 1, y)


def test_walking_faces_each_step_and_stopping_off_a_spot_keeps_the_last_facing() -> None:
    village = Village()
    village.movement.place("mei", MapTile(map=SQUARE, x=40, y=15))
    village.moves.clear()

    village.finish(village.movement.walk_to("mei", MapTile(map=SQUARE, x=38, y=15)))

    assert [(m.x, m.pose, m.facing) for m in village.moves] == [
        (39, Pose.WALKING, Facing.WEST),
        (38, Pose.STANDING, Facing.WEST),
    ]


def test_stopping_mid_walk_on_a_spot_takes_its_pose() -> None:
    village = Village()
    bench = MAPS[SQUARE].spot_at(52, 15)
    assert bench is not None and bench.kind is SpotKind.SEAT
    village.movement.place("mei", MapTile(map=SQUARE, x=bench.x - 1, y=bench.y))
    walk = village.movement.walk_to("mei", MapTile(map=SQUARE, x=bench.x + 3, y=bench.y))

    def stop_on_the_bench(moved: EntityMoved) -> None:
        if (moved.x, moved.y) == (bench.x, bench.y) and not walk.done:
            village.movement.stop("mei")

    village.world.bus.subscribe(EntityMoved, stop_on_the_bench)
    village.finish(walk)

    assert village.movement.posture("mei") == (Pose.SITTING, bench.facing)


def test_a_muralist_works_on_the_spot_others_look_from() -> None:
    village = Village()
    wall = TOWN.murals[0]
    assert wall.map is not None
    stand = MapTile(map=wall.map, x=wall.stand.x, y=wall.stand.y)

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

    village.movement.place("mei", MapTile(map=UPSTAIRS, x=x, y=y))

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
    seats = spots(UPSTAIRS, SpotKind.SEAT)
    kinds = {SpotKind.SEAT: 0.0}

    favourites = {
        entity: choose(entity, seats, kinds, {}, None, lambda a, b: 0.0)
        for entity in ("ada", "mei", "kofi", "ingrid", "tobias")
    }

    assert len(set(favourites.values())) > 1
    assert all(0 <= taste(entity, seats[0]) <= 1 for entity in favourites)
    assert favourites["ada"] == choose("ada", seats, kinds, {}, None, lambda a, b: 0.0)


def test_regulars_keep_their_usual_seats_from_todays_map_ids() -> None:
    seats = spots(UPSTAIRS, SpotKind.SEAT)
    today = [replace(seat, map="coffee_shop") for seat in seats]
    kinds = {SpotKind.SEAT: 0.0}

    for entity in ("ada", "mei", "kofi", "ingrid", "tobias"):
        here = choose(entity, seats, kinds, {}, None, lambda a, b: 0.0, place="coffee_shop")
        before = choose(entity, today, kinds, {}, None, lambda a, b: 0.0)
        assert here is not None and before is not None
        assert here.id == before.id
        assert taste(entity, here, "coffee_shop") == taste(entity, before)
