import asyncio
import math
from datetime import UTC, datetime, timedelta

import pytest

from simile.schema import PLAYER_ID, VILLAGE_MAP, Location, LocationKind, MapTile, Tile
from simile.sim import STEP, Clock, EntityMoved, FakeWallClock, World
from simile.world import Movement, Outcome, Point, Walk
from simile.world.map import WALKING_SPEED, TownMap, load_map, load_maps
from simile.world.movement import inside
from simile.world.paths import DOOR

TOWN = load_map()
MAPS = load_maps()
HOUSES = [location for location in TOWN.locations if location.kind is LocationKind.HOUSE]
START = datetime(2026, 1, 1, 8, tzinfo=UTC)
[CAFE_DOOR] = [door for door in TOWN.doors if door.id == "coffee_shop"]
[COUNTER] = MAPS["coffee_shop"].interactables
FRONT = MapTile(map="coffee_shop", x=COUNTER.stand[0].x, y=COUNTER.stand[0].y)


class Village:
    def __init__(self, town: TownMap | dict[str, TownMap] = MAPS) -> None:
        self.world = World(Clock(START), FakeWallClock())
        self.movement = Movement(town, self.world.bus)
        self.world.loop.register(self.movement)
        self.moves: list[tuple[float, EntityMoved]] = []
        self.world.bus.subscribe(EntityMoved, lambda event: self.moves.append((self.now, event)))

    @property
    def now(self) -> float:
        return (self.world.clock.now - START).total_seconds()

    def run(self, seconds: float) -> None:
        for _ in range(round(seconds / STEP)):
            self.world.loop.tick()

    def finish(self, *walks: Walk, limit: float = 300) -> None:
        while not all(walk.done for walk in walks):
            assert self.now < limit, walks
            self.world.loop.tick()

    def tiles(self, entity: str) -> list[tuple[float, float]]:
        return [(event.x, event.y) for _, event in self.moves if event.entity == entity]

    def spots(self, entity: str) -> list[tuple[str, float, float]]:
        return [(e.map, e.x, e.y) for _, e in self.moves if e.entity == entity]


def entry_of(location: Location) -> MapTile:
    return MapTile(map=location.map, x=location.entry.x, y=location.entry.y)


def assert_on_time(elapsed: float, distance: float) -> None:
    assert -1e-9 <= elapsed - distance / WALKING_SPEED < STEP


def corridor(length: int) -> TownMap:
    return TownMap("corridor", length, 1, ((False,) * length,), ())


def open_field(size: int) -> TownMap:
    return TownMap("field", size, size, ((False,) * size,) * size, ())


def test_walks_at_walking_speed() -> None:
    village = Village(corridor(14))
    village.movement.place("mei", Tile(x=0, y=0))

    walk = village.movement.walk_to("mei", Tile(x=13, y=0))
    village.run(0.5)

    assert village.movement.position("mei").x == pytest.approx(0.5 * WALKING_SPEED)
    village.run(10 - 0.5 - STEP)
    assert not walk.done
    village.run(STEP)
    assert walk.outcome is Outcome.ARRIVED
    assert village.movement.position("mei") == (13, 0)
    assert walk.distance == 13


def test_publishes_once_per_tile_as_it_reaches_it() -> None:
    village = Village(corridor(14))
    village.movement.place("mei", Tile(x=0, y=0))
    village.moves.clear()

    village.finish(village.movement.walk_to("mei", Tile(x=13, y=0)))

    assert village.tiles("mei") == [(x, 0) for x in range(1, 14)]
    for (when, _), x in zip(village.moves, range(1, 14), strict=True):
        assert_on_time(when, x)


def test_publishes_per_tile_not_per_tick_at_10x() -> None:
    village = Village(corridor(14))
    village.world.clock.speed = 10
    village.movement.place("mei", Tile(x=0, y=0))
    village.moves.clear()

    walk = village.movement.walk_to("mei", Tile(x=13, y=0))
    asyncio.run(village.world.loop.run(timedelta(seconds=10)))

    assert walk.outcome is Outcome.ARRIVED
    assert village.world.loop.wall.now() == pytest.approx(1)
    assert len(village.moves) == 13


def test_takes_longer_on_a_diagonal() -> None:
    village = Village(open_field(3))
    village.movement.place("mei", Tile(x=0, y=0))

    walk = village.movement.walk_to("mei", Tile(x=2, y=2))
    village.finish(walk)

    assert walk.distance == pytest.approx(2 * math.sqrt(2))
    assert_on_time(village.now, walk.distance)
    assert village.tiles("mei")[1:] == [(1, 1), (2, 2)]


@pytest.mark.parametrize("house", HOUSES, ids=lambda house: house.id)
def test_walks_from_every_house_to_the_coffee_shop(house) -> None:
    village = Village()
    village.movement.place("mei", house.id)
    village.moves.clear()

    walk = village.movement.walk_to("mei", "coffee_shop")
    village.finish(walk)

    entry = TOWN.location("coffee_shop").entry
    assert walk.outcome is Outcome.ARRIVED
    assert walk.destination == entry_of(TOWN.location("coffee_shop"))
    assert village.movement.position("mei") == (entry.x, entry.y)
    assert_on_time(village.now, walk.distance)
    steps = [(house.entry.x, house.entry.y), *village.tiles("mei")]
    for (x, y), (nx, ny) in zip(steps, steps[1:], strict=False):
        assert max(abs(nx - x), abs(ny - y)) == 1


def test_npcs_going_to_the_same_place_end_on_different_tiles() -> None:
    village = Village()
    npcs = [f"npc_{n}" for n in range(5)]
    for npc, house in zip(npcs, HOUSES, strict=False):
        village.movement.place(npc, house.id)

    walks = [village.movement.walk_to(npc, "terminal_1") for npc in npcs]
    village.finish(*walks)

    tiles = {village.movement.position(npc) for npc in npcs}
    terminal = TOWN.location("terminal_1")
    assert all(walk.outcome is Outcome.ARRIVED for walk in walks)
    assert len(tiles) == len(npcs)
    assert sum(inside(terminal, (int(x), int(y))) for x, y in tiles) == 2
    assert all(TOWN.walkable(int(x), int(y)) for x, y in tiles)


def test_two_npcs_walking_to_the_same_tile_end_side_by_side() -> None:
    village = Village(open_field(9))
    village.movement.place("mei", Tile(x=0, y=0))
    village.movement.place("suki", Tile(x=8, y=8))

    walks = [village.movement.walk_to(npc, Tile(x=4, y=4)) for npc in ("mei", "suki")]
    village.finish(*walks)

    assert walks[0].destination == MapTile(map="field", x=4, y=4)
    assert walks[1].destination != MapTile(map="field", x=4, y=4)
    mei, suki = village.movement.position("mei"), village.movement.position("suki")
    assert max(abs(mei.x - suki.x), abs(mei.y - suki.y)) == 1


def test_walking_to_someone_ends_next_to_them() -> None:
    village = Village(open_field(9))
    village.movement.place("mei", Tile(x=0, y=0))
    village.movement.place("suki", Tile(x=6, y=3))

    village.finish(village.movement.walk_to("mei", Tile(x=6, y=3)))

    assert village.movement.position("mei") == (5, 2)


def test_steps_aside_when_someone_is_standing_on_the_destination() -> None:
    village = Village(corridor(10))
    village.movement.place("mei", Tile(x=0, y=0))
    walk = village.movement.walk_to("mei", Tile(x=5, y=0))
    village.run(1)

    village.movement.track(PLAYER_ID, Point(5.2, 0, "corridor"))
    village.finish(walk)

    assert walk.outcome is Outcome.ARRIVED
    assert walk.destination == MapTile(map="corridor", x=4, y=0)
    assert walk.distance == 4
    assert village.movement.position("mei") == (4, 0)


def test_stopping_cancels_the_walk_and_ends_on_the_next_tile() -> None:
    village = Village(corridor(14))
    village.movement.place("mei", Tile(x=0, y=0))
    walk = village.movement.walk_to("mei", Tile(x=13, y=0))
    village.run(2)

    village.movement.stop("mei")

    assert walk.outcome is Outcome.CANCELLED
    village.run(5)
    assert village.movement.position("mei") == (3, 0)
    assert village.tiles("mei")[-1] == (3, 0)


@pytest.mark.parametrize("stop", ["stop", "unreachable"])
def test_stopping_steps_off_a_tile_someone_else_has(stop: str) -> None:
    village = Village(TownMap("corridor", 13, 1, ((False,) * 12 + (True,),), ()))
    village.movement.place("b", Tile(x=2, y=0))
    village.movement.place("a", Tile(x=0, y=0))
    village.movement.walk_to("a", Tile(x=11, y=0))
    village.run(1)
    assert 1 < village.movement.position("a").x < 2

    if stop == "stop":
        village.movement.stop("a")
    else:
        village.movement.walk_to("a", Tile(x=12, y=0))
    village.run(5)

    assert village.movement.position("b") == (2, 0)
    assert village.movement.position("a") in ((1, 0), (3, 0))
    assert village.tiles("a")[-1] == village.movement.position("a")


def test_a_new_walk_supersedes_the_last() -> None:
    village = Village(corridor(14))
    village.movement.place("mei", Tile(x=5, y=0))
    first = village.movement.walk_to("mei", Tile(x=13, y=0))
    village.run(1)

    second = village.movement.walk_to("mei", Tile(x=0, y=0))

    assert first.outcome is Outcome.SUPERSEDED
    assert second.destination == MapTile(map="corridor", x=0, y=0)
    assert second.distance == pytest.approx((7 - (5 + WALKING_SPEED)) + 7)
    village.finish(second)
    assert second.outcome is Outcome.ARRIVED
    assert village.tiles("mei") == [(5, 0), (6, 0), (7, 0), *[(x, 0) for x in range(6, -1, -1)]]


def test_a_walk_to_a_wall_is_unreachable() -> None:
    village = Village(TownMap("walled", 3, 1, ((False, True, False),), ()))
    village.movement.place("mei", Tile(x=0, y=0))

    walls = village.movement.walk_to("mei", Tile(x=1, y=0))
    beyond = village.movement.walk_to("mei", Tile(x=2, y=0))

    assert walls.outcome is beyond.outcome is Outcome.UNREACHABLE
    village.run(1)
    assert village.movement.position("mei") == (0, 0)


def test_arrives_at_once_if_already_there() -> None:
    village = Village()
    village.movement.place("mei", "coffee_shop")
    village.moves.clear()

    walk = village.movement.walk_to("mei", "coffee_shop")

    assert walk.outcome is Outcome.ARRIVED
    assert walk.distance == 0
    village.run(1)
    assert village.moves == []


def test_place_publishes_and_keeps_entities_apart() -> None:
    village = Village()

    mei = village.movement.place("mei", "house_1")
    suki = village.movement.place("suki", "house_1")

    house = TOWN.location("house_1")
    assert mei == entry_of(house)
    assert suki != mei and inside(house, (suki.x, suki.y))
    assert village.tiles("mei") == [(mei.x, mei.y)]
    assert village.tiles("suki") == [(suki.x, suki.y)]


def test_place_cancels_a_walk() -> None:
    village = Village()
    village.movement.place("mei", "house_1")
    walk = village.movement.walk_to("mei", "coffee_shop")
    village.run(1)

    village.movement.place("mei", "square")

    assert walk.outcome is Outcome.CANCELLED
    village.run(5)
    square = TOWN.location("square").entry
    assert village.movement.position("mei") == (square.x, square.y)


def test_cannot_place_on_a_wall() -> None:
    with pytest.raises(ValueError):
        Village(corridor(3)).movement.place("mei", Tile(x=5, y=0))


def test_unknown_locations_and_entities_raise() -> None:
    village = Village()
    village.movement.place("mei", "house_1")

    with pytest.raises(KeyError):
        village.movement.walk_to("mei", "moon")
    with pytest.raises(KeyError):
        village.movement.walk_to("nobody", "square")


def test_tracks_the_player_without_publishing() -> None:
    village = Village()

    village.movement.track(PLAYER_ID, Point(31.4, 21.6))

    assert village.movement.position(PLAYER_ID) == (31.4, 21.6)
    assert village.movement.entities() == {PLAYER_ID: (31.4, 21.6)}
    assert village.moves == []
    assert village.movement.place("mei", Tile(x=31, y=22)) != MapTile(map=VILLAGE_MAP, x=31, y=22)


def test_lists_entities_and_distances() -> None:
    village = Village(open_field(9))
    village.movement.place("mei", Tile(x=0, y=0))
    village.movement.place("suki", Tile(x=3, y=4))

    assert village.movement.entities() == {"mei": (0, 0), "suki": (3, 4)}
    assert village.movement.distance("mei", "suki") == 5


def test_a_walk_can_be_awaited() -> None:
    village = Village()
    village.movement.place("mei", "house_3")

    async def walk_to_the_coffee_shop() -> tuple[Outcome, Outcome]:
        loop = asyncio.create_task(village.world.loop.run(timedelta(minutes=1)))
        walk = village.movement.walk_to("mei", "coffee_shop")
        outcome = await walk
        again = await walk
        village.world.loop.stop()
        await loop
        return outcome, again

    assert asyncio.run(walk_to_the_coffee_shop()) == (Outcome.ARRIVED, Outcome.ARRIVED)
    assert village.now < 60


def test_callbacks_hear_how_a_walk_ended() -> None:
    village = Village()
    village.movement.place("mei", "house_1")
    heard: list[Outcome | None] = []

    walk = village.movement.walk_to("mei", "square")
    walk.add_done_callback(lambda walk: heard.append(walk.outcome))
    village.movement.walk_to("mei", "park")
    walk.add_done_callback(lambda walk: heard.append(walk.outcome))

    assert heard == [Outcome.SUPERSEDED, Outcome.SUPERSEDED]


def test_a_callback_can_start_the_next_walk() -> None:
    village = Village()
    village.movement.place("mei", "house_1")
    walks = [village.movement.walk_to("mei", "coffee_shop")]
    walks[0].add_done_callback(lambda _: walks.append(village.movement.walk_to("mei", "square")))

    village.movement.place("mei", "house_2")
    village.finish(walks[-1])

    assert [walk.outcome for walk in walks] == [Outcome.CANCELLED, Outcome.ARRIVED]
    assert walks[1].destination == entry_of(TOWN.location("square"))


def test_placing_someone_from_a_callback_mid_tick_publishes_no_stale_move() -> None:
    village = Village(corridor(12))
    village.movement.place("a", Tile(x=0, y=0))
    village.movement.place("b", Tile(x=5, y=0))
    walk = village.movement.walk_to("a", Tile(x=1, y=0))
    village.movement.walk_to("b", Tile(x=11, y=0))
    walk.add_done_callback(lambda _: village.movement.place("b", Tile(x=9, y=0)))
    village.moves.clear()

    village.finish(walk)
    village.run(1)

    assert village.tiles("b") == [(9, 0)]


def test_a_failing_callback_is_logged_and_the_others_still_run(
    caplog: pytest.LogCaptureFixture,
) -> None:
    village = Village(corridor(3))
    village.movement.place("mei", Tile(x=0, y=0))
    heard: list[Walk] = []

    def fail(walk: Walk) -> None:
        raise RuntimeError("boom")

    walk = village.movement.walk_to("mei", Tile(x=1, y=0))
    walk.add_done_callback(fail)
    walk.add_done_callback(heard.append)
    village.finish(walk)
    walk.add_done_callback(fail)

    assert heard == [walk]
    assert caplog.text.count("RuntimeError: boom") == 2


def assert_steps_between_neighbours(spots: list[tuple[str, float, float]]) -> list[int]:
    """Where the walk changes map."""
    crossings = []
    for n, ((map_a, x, y), (map_b, nx, ny)) in enumerate(zip(spots, spots[1:], strict=False)):
        if map_a == map_b:
            assert max(abs(nx - x), abs(ny - y)) == 1, (spots[n], spots[n + 1])
        else:
            crossings.append(n + 1)
    return crossings


def door_ends(door_map: str) -> tuple[tuple[str, float, float], tuple[str, float, float]]:
    outside, inside = CAFE_DOOR.outside, CAFE_DOOR.inside
    ends = ((outside.map, outside.x, outside.y), (inside.map, inside.x, inside.y))
    return ends if door_map == VILLAGE_MAP else (ends[1], ends[0])


def test_walks_from_a_house_to_the_coffee_shop_counter_and_back_through_the_door() -> None:
    village = Village()
    village.movement.place("mei", "house_1")
    village.moves.clear()

    there = village.movement.walk_to("mei", FRONT)
    village.finish(there)

    assert there.outcome is Outcome.ARRIVED
    assert there.destination == FRONT
    assert village.movement.position("mei") == Point(FRONT.x, FRONT.y, "coffee_shop")
    assert_on_time(village.now, there.distance)
    home = TOWN.location("house_1").entry
    spots = [(VILLAGE_MAP, home.x, home.y), *village.spots("mei")]
    [crossing] = assert_steps_between_neighbours(spots)
    assert (spots[crossing - 1], spots[crossing]) == door_ends(VILLAGE_MAP)

    village.moves.clear()
    back = village.movement.walk_to("mei", "house_1")
    village.finish(back)

    assert back.outcome is Outcome.ARRIVED
    assert village.movement.position("mei") == Point(home.x, home.y)
    assert back.distance == pytest.approx(there.distance)
    spots = [("coffee_shop", FRONT.x, FRONT.y), *village.spots("mei")]
    [crossing] = assert_steps_between_neighbours(spots)
    assert (spots[crossing - 1], spots[crossing]) == door_ends("coffee_shop")


def test_going_through_a_door_publishes_a_jump_onto_the_other_map_a_step_later() -> None:
    village = Village()
    outside, inside = CAFE_DOOR.outside, CAFE_DOOR.inside
    village.movement.place("mei", MapTile(map=VILLAGE_MAP, x=outside.x, y=outside.y + 1))
    village.moves.clear()

    walk = village.movement.walk_to("mei", MapTile(map=inside.map, x=inside.x, y=inside.y - 1))
    village.finish(walk)

    [(stepped, doorstep), (jumped, mat), (_, last)] = village.moves
    assert (doorstep.map, doorstep.x, doorstep.y) == (VILLAGE_MAP, outside.x, outside.y)
    assert (mat.map, mat.x, mat.y) == (inside.map, inside.x, inside.y)
    assert (last.map, last.x, last.y) == (inside.map, inside.x, inside.y - 1)
    assert_on_time(stepped, 1)
    assert_on_time(jumped, 1 + DOOR)
    assert walk.distance == 2 + DOOR


def test_position_stays_on_the_doorstep_until_through_and_a_stop_still_goes_through() -> None:
    village = Village()
    outside, inside = CAFE_DOOR.outside, CAFE_DOOR.inside
    village.movement.place("mei", MapTile(map=VILLAGE_MAP, x=outside.x, y=outside.y))
    walk = village.movement.walk_to("mei", MapTile(map=inside.map, x=inside.x, y=inside.y - 2))
    village.run(DOOR / WALKING_SPEED / 2)

    assert village.movement.position("mei") == Point(outside.x, outside.y)
    village.movement.stop("mei")
    village.run(1)

    assert walk.outcome is Outcome.CANCELLED
    assert village.movement.position("mei") == Point(inside.x, inside.y, inside.map)


def test_a_walker_on_a_doorstep_that_hasnt_set_off_stays_put() -> None:
    village = Village()
    outside, inside = CAFE_DOOR.outside, CAFE_DOOR.inside
    village.movement.place("mei", MapTile(map=VILLAGE_MAP, x=outside.x, y=outside.y))
    walk = village.movement.walk_to("mei", MapTile(map=inside.map, x=inside.x, y=inside.y - 2))

    village.movement.stop("mei")
    village.run(1)

    assert walk.outcome is Outcome.CANCELLED
    assert village.movement.position("mei") == Point(outside.x, outside.y)
    village.movement.walk_to("mei", MapTile(map=inside.map, x=inside.x, y=inside.y - 2))
    away = village.movement.walk_to("mei", Tile(x=outside.x, y=outside.y + 2))
    village.finish(away)
    assert away.distance == 2
    assert village.spots("mei")[-2:] == [
        (VILLAGE_MAP, outside.x, outside.y + 1),
        (VILLAGE_MAP, outside.x, outside.y + 2),
    ]


def test_distance_between_maps_is_infinite() -> None:
    village = Village()
    village.movement.place("mei", FRONT)
    village.movement.place("suki", "coffee_shop_staff")
    village.movement.place("kofi", Tile(x=FRONT.x, y=FRONT.y + 30))

    assert village.movement.distance("mei", "suki") == pytest.approx(2)
    assert village.movement.distance("mei", "kofi") == math.inf
    assert village.movement.position("kofi").map == VILLAGE_MAP


def test_a_tracked_player_inside_reports_the_interiors_map() -> None:
    village = Village()

    village.movement.track(PLAYER_ID, Point(10, 12.5, "coffee_shop"))

    assert village.movement.position(PLAYER_ID).map == "coffee_shop"
    assert village.movement.entities()[PLAYER_ID] == Point(10, 12.5, "coffee_shop")
    mat = MapTile(map="coffee_shop", x=10, y=13)
    assert village.movement.place("mei", mat) != mat
    assert village.movement.place("suki", Tile(x=10, y=13)) == MapTile(map=VILLAGE_MAP, x=10, y=13)


def test_locations_on_two_maps_are_the_villages() -> None:
    village = Village()
    village.movement.place("mei", "house_1")

    for location_id in ("coffee_shop", "noodle_bar", "maker_space"):
        assert village.movement.town.location(location_id).map == VILLAGE_MAP
    assert village.movement.town.location("coffee_shop_queue").map == "coffee_shop"
    village.finish(walk := village.movement.walk_to("mei", "coffee_shop"))
    assert walk.outcome is Outcome.ARRIVED
    assert village.movement.position("mei").map == VILLAGE_MAP


def test_walks_into_the_gallery_through_its_door() -> None:
    village = Village()
    village.movement.place("mei", "square")

    village.finish(walk := village.movement.walk_to("mei", "gallery"))

    assert walk.outcome is Outcome.ARRIVED
    assert walk.destination == entry_of(MAPS["gallery"].location("gallery"))
    assert village.movement.position("mei").map == "gallery"


def test_nobody_reaches_a_map_without_a_door() -> None:
    village = Village({**MAPS, "field": open_field(3)})
    village.movement.place("mei", "square")

    field = MapTile(map="field", x=1, y=1)
    assert village.movement.walk_to("mei", field).outcome is Outcome.UNREACHABLE
    with pytest.raises(KeyError):
        village.movement.walk_to("mei", MapTile(map="moon", x=0, y=0))


def test_points_compare_their_maps_but_measure_as_pairs() -> None:
    inside, outside = Point(5, 6, "coffee_shop"), Point(5, 6)

    assert inside != outside and inside == (5, 6) == outside
    assert outside.map == VILLAGE_MAP and len({inside, outside}) == 2
    assert math.dist(inside, Point(8, 10)) == 5
    x, y = inside
    assert (x, y, inside.x, inside.y) == (5, 6, 5, 6)
    assert repr(inside) == "Point(5, 6, 'coffee_shop')"
