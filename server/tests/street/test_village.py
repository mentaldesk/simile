import itertools
import json
import re
from collections import deque
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image
from typer.testing import CliRunner

from simile.cli import create_cli
from simile.schema import DoorKind, Facing, InteractableKind, MapTile, Pose
from simile.sim import Clock, EntityMoved, FakeWallClock, World
from simile.street.metro import GANTRY, HIGH_LEDGE, METRO
from simile.street.plan import (
    BUILDINGS_LAYER,
    CREATURES_LAYER,
    FURNITURE_LAYER,
    LIGHT_LAYER,
    PICKUPS_LAYER,
)
from simile.street.sewers import SEWERS
from simile.street.village import (
    FLOOR_ROW,
    GROUND,
    JUMPING,
    STOOL_M,
    STOREY,
    UNDERGROUND,
    village,
)
from simile.world import Movement, Outcome, Walk
from simile.world.map import (
    STREET_DIR,
    WALKING_SPEED,
    MapKind,
    SpotKind,
    TownMap,
    load_maps,
    with_every_location,
)
from simile.world.map import Spot as MapSpot
from simile.world.movement import Point, inside
from simile.world.paths import Spot, door_ends, find_route, route_length, steps
from simile.world.spots import Purpose

MAPS = load_maps(STREET_DIR)
TOWN = with_every_location(MAPS)
STREETS = [town for town in MAPS.values() if town.kind is MapKind.STREET]
FLOORS = [town for town in MAPS.values() if town.kind is MapKind.FLOOR]
START = datetime(2026, 1, 1, 8, tzinfo=UTC)


def floors_of(location_id: str) -> list[TownMap]:
    return [town for town in FLOORS if town.building == location_id]


def test_the_committed_maps_are_up_to_date(tmp_path: Path) -> None:
    result = CliRunner().invoke(create_cli(), ["street", "--out", str(tmp_path)])

    assert result.exit_code == 0, result.output
    stale = "content/street is out of date: run `cd server && uv run simile street`"

    def generated(root: Path) -> set[str]:
        return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.suffix != ".md"}

    names = generated(tmp_path)
    assert generated(STREET_DIR) == names, stale
    for name in sorted(names):
        new, old = tmp_path / name, STREET_DIR / name
        if new.suffix in (".tmj", ".json"):
            assert new.read_bytes() == old.read_bytes(), f"{name}: {stale}"
        elif new.suffix == ".png":
            with Image.open(new) as a, Image.open(old) as b:
                assert (
                    a.size == b.size and a.convert("RGBA").tobytes() == b.convert("RGBA").tobytes()
                ), f"{name}: {stale}"
        elif new.is_file():
            raise AssertionError(f"{name}: nothing compares it")


def test_no_map_id_is_one_of_the_iso_villages() -> None:
    assert not set(MAPS) & {"village", "coffee_shop", "gallery", "maker_space", "noodle_bar"}


def test_every_map_is_a_side_view_street_or_floor() -> None:
    assert [town.id for town in STREETS] == [
        "banyan_row",
        "high_street",
        "kapok_walk",
        "lychee_lane",
        "metro",
        "rooftops",
        "sewers",
    ]
    assert len(FLOORS) == 32
    assert len(STREETS) + len(FLOORS) == len(MAPS)
    for floor in FLOORS:
        assert floor.id == f"{floor.building}_floor_{floor.floor}"
        assert floor.height == STOREY


def test_every_stop_is_a_standing_cell() -> None:
    for town in MAPS.values():
        stops = [(f"spot {s.id}", s.x, s.y) for s in town.spots]
        stops += [(f"entry of {loc.id}", loc.entry.x, loc.entry.y) for loc in town.locations]
        stops += [(f"{i.id}'s stand", t.x, t.y) for i in town.interactables for t in i.stand]
        stops += [(f"{w.id}'s stand", w.stand.x, w.stand.y) for w in town.murals]
        stops += [
            (f"{door.id}'s end", end.x, end.y)
            for door in town.doors
            for end in (door.outside, door.inside)
            if end.map == town.id
        ]
        for what, x, y in stops:
            assert town.standing(x, y), f"{what} on {town.id}"


def test_rooms_are_wide_enough_for_every_spot() -> None:
    for town in MAPS.values():
        cells = [(spot.x, spot.y) for spot in town.spots]
        assert len(cells) == len(set(cells)), town.id


def test_every_entry_and_spot_is_in_its_place() -> None:
    for town in MAPS.values():
        for location in town.locations:
            assert inside(location, Point(location.entry.x, location.entry.y, town.id))
    for location in TOWN.locations:
        if location.floors:
            for floor in location.floors:
                spots = MAPS[floor.map].spots
                assert all(inside(location, Point(s.x, s.y, s.map)) for s in spots)


def reachable(start: Spot, jumps: bool = False) -> set[Spot]:
    doors = door_ends(MAPS)
    seen, queue = {start}, deque([start])
    while queue:
        here = queue.popleft()
        cells = steps(MAPS[here.map], (here.x, here.y), jumps)
        nexts = [Spot(here.map, *cell) for cell, _ in cells]
        if here in doors:
            nexts.append(doors[here])
        for there in nexts:
            if there not in seen:
                seen.add(there)
                queue.append(there)
    return seen


[LEDGE] = [item for item in MAPS[METRO].interactables if item.id == HIGH_LEDGE]
LOCKED = (
    {Spot(METRO, t.x, t.y) for t in LEDGE.stand}
    | {Spot(METRO, x, 5) for x in (85, 86)}
    | {Spot(METRO, x, GANTRY) for x in (61, 62, 63)}
    | {Spot(METRO, x, GANTRY - 5) for x in range(58, 74)}
)
"""Out of reach until legs open them, and the gantry's roof, which nobody reaches."""


def test_every_cell_of_every_map_but_the_locked_ones_is_reachable_from_every_street() -> None:
    every_cell = {
        Spot(town.id, x, y)
        for town in MAPS.values()
        if town.id != SEWERS
        for y in range(town.height)
        for x in range(town.width)
        if town.walkable(x, y)
    } - LOCKED
    jumped = {cell for cell in every_cell if cell.map in JUMPING}
    for street in STREETS:
        start = next(
            Spot(street.id, x, GROUND) for x in range(street.width) if street.standing(x, GROUND)
        )
        found = {cell for cell in reachable(start, jumps=True) if cell.map != SEWERS}
        assert found == every_cell, street.id
        walked = reachable(start)
        assert every_cell - jumped <= walked, street.id
        assert jumped - walked, f"{street.id}: nothing on the rooftops needs a jump"


def test_every_stair_and_ladder_end_is_reachable_from_its_floor() -> None:
    climbs = [door for door in TOWN.doors if door.kind in (DoorKind.STAIRS, DoorKind.LADDER)]
    ends = [
        (door.id, end.map, (end.x, end.y)) for door in climbs for end in (door.outside, door.inside)
    ]
    ends += [
        (f"{town.id}'s {town.climb(x, y)}", town.id, (x, y))
        for town in STREETS
        if town.id != SEWERS
        for y in range(town.height)
        for x in range(town.width)
        if town.climb(x, y) is not None
    ]
    assert len(ends) > 2 * len(climbs)
    for what, map_id, end in ends:
        town = MAPS[map_id]
        cells = [
            (x, y) for y in range(town.height) for x in range(town.width) if town.standing(x, y)
        ]
        jumps = map_id in JUMPING
        for cell in cells:
            route = find_route(
                {map_id: town}, Spot(map_id, *cell), Spot(map_id, *end), {}, jumps=jumps
            )
            assert route is not None, f"{what} from {cell} on {map_id}"


def test_no_flight_or_ladder_starts_against_an_outer_wall() -> None:
    for door in TOWN.doors:
        foot, top = door.outside, door.inside
        town = MAPS[foot.map]
        if door.kind is DoorKind.STAIRS:
            behind = foot.x + (1 if top.x < foot.x else -1)
            assert town.standing(behind, foot.y), door.id
        elif door.kind is DoorKind.LADDER:
            assert town.standing(foot.x - 1, foot.y) and town.standing(foot.x + 1, foot.y), door.id


def test_streets_join_through_doors_outside_on_the_first_street() -> None:
    joins = {
        door.id: (door.outside.map, door.inside.map)
        for door in TOWN.doors
        if MAPS[door.inside.map].kind is MapKind.STREET
    }

    assert joins == {
        "banyan_row_to_high_street": ("banyan_row", "high_street"),
        "high_street_to_kapok_walk": ("high_street", "kapok_walk"),
        "high_street_to_lychee_lane": ("high_street", "lychee_lane"),
        "kapok_walk_to_rooftops": ("kapok_walk", "rooftops"),
        "banyan_row_to_metro": ("banyan_row", "metro"),
        "metro_to_sewers": ("metro", "sewers"),
    }
    assert {door.kind for door in TOWN.doors if door.id in joins} == {DoorKind.DOOR}


def test_floors_join_by_stairs_ladders_and_lifts_with_an_end_tile_each() -> None:
    links = [door for door in TOWN.doors if door.kind is not DoorKind.DOOR]
    kinds = {door.kind for door in links}
    ends = [(end.map, end.x, end.y) for door in TOWN.doors for end in (door.outside, door.inside)]

    assert kinds == {DoorKind.STAIRS, DoorKind.LADDER, DoorKind.LIFT}
    assert len(ends) == len(set(ends))
    for door in links:
        low, high = MAPS[door.outside.map], MAPS[door.inside.map]
        assert low.building == high.building and low.floor < high.floor, door.id
        if door.kind is not DoorKind.LIFT:
            assert high.floor == low.floor + 1, door.id
    lifts = {door.id for door in links if door.kind is DoorKind.LIFT}
    assert lifts == {"gallery_lift_0_1", "gallery_lift_0_2", "gallery_lift_1_2"}


def test_no_two_openings_on_a_street_are_closer_than_three_tiles() -> None:
    for street in STREETS:
        ends = sorted(
            end.x
            for door in street.doors
            for end in (door.outside, door.inside)
            if end.map == street.id
        )
        gaps = {(a, b) for a, b in itertools.pairwise(ends) if b - a < 3}
        assert not gaps, street.id


def test_a_building_is_one_location_arriving_on_its_ground_floor() -> None:
    for location in TOWN.locations:
        floors = floors_of(location.id)
        if not floors:
            continue
        ground = MAPS[location.map]
        assert ground.floor == 0 and ground.building == location.id
        assert sorted(f.map for f in location.floors) == sorted(t.id for t in floors[1:])
        [front_door] = [d for d in TOWN.doors if d.id == location.id]
        assert MAPS[front_door.outside.map].kind is MapKind.STREET
        assert front_door.inside.map == location.map


def test_each_floor_says_where_its_building_stands() -> None:
    for floor in FLOORS:
        data = json.loads((STREET_DIR / "floors" / f"{floor.id}.tmj").read_text())
        props = {p["name"]: p["value"] for p in data["properties"]}
        street = MAPS[props["street"]]
        street_data = json.loads((STREET_DIR / f"{street.id}.tmj").read_text())
        [facade] = [
            o
            for layer in street_data["layers"]
            if layer["name"] == BUILDINGS_LAYER
            for o in layer["objects"]
            if o["name"] == floor.building
        ]
        assert props["street_x"] * 16 == facade["x"]
        assert props["street_y"] == GROUND - FLOOR_ROW - STOREY * floor.floor
        assert floor.width * 16 == facade["width"]
        door = next(d for d in TOWN.doors if d.id == floor.building)
        if floor.floor == 0:
            assert door.outside.x == props["street_x"] + door.inside.x


def test_every_mural_wall_is_on_a_street_facing_the_camera() -> None:
    walls = [(town, wall) for town in MAPS.values() for wall in town.murals]

    assert walls
    for town, wall in walls:
        assert town.kind is MapKind.STREET
        assert wall.face == "south"
        assert wall.stand.y == wall.y and wall.x <= wall.stand.x < wall.x + wall.width
        spot = town.spot_at(wall.stand.x, wall.stand.y)
        assert spot is not None and spot.kind is SpotKind.VIEWING and spot.facing is Facing.NORTH


def test_spots_face_to_suit_the_side_view() -> None:
    for town in MAPS.values():
        for spot in town.spots:
            if spot.kind in (SpotKind.TERMINAL, SpotKind.DESK, SpotKind.VIEWING):
                assert spot.facing is Facing.NORTH, spot.id
            assert spot.dx == spot.dy == 0, spot.id
            assert spot.facing in (Facing.NORTH, Facing.EAST, Facing.WEST) or (
                spot.kind is SpotKind.STANDING and spot.facing is Facing.SOUTH
            ), spot.id


SEATS = {"stool", "bench", "cafe_table", "noodle_table"}
"""What there is to sit on: a table's piece has its chairs."""
PLANS = {plan.id: plan for plan in village()}


def pieces_at(x: int, y: int, plan_id: str) -> set[str]:
    plan = PLANS[plan_id]
    return {
        piece.name
        for piece in plan.furniture
        if piece.area.x <= x < piece.area.x + piece.area.width
        and piece.area.y <= y < piece.area.y + piece.area.height
    }


def test_every_seat_faces_east_or_west_on_something_to_sit_on() -> None:
    kinds = (SpotKind.SEAT, SpotKind.BAR)
    seats = [spot for town in MAPS.values() for spot in town.spots if spot.kind in kinds]

    assert len(seats) == 64
    for seat in seats:
        assert seat.facing in (Facing.EAST, Facing.WEST), seat.id
        assert pieces_at(seat.x, seat.y, seat.map) & SEATS, seat.id
    benches = [seat for seat in seats if MAPS[seat.map].kind is MapKind.STREET]
    assert {seat.facing for seat in benches} == {Facing.EAST, Facing.WEST}


def stools_at(map_id: str) -> list[MapSpot]:
    return [s for s in MAPS[map_id].spots if "stool" in pieces_at(s.x, s.y, map_id)]


def test_the_daily_grinds_bar_has_a_stool_at_each_of_its_old_spots_facing_the_counter() -> None:
    bar = stools_at("coffee_shop_floor_0")
    counter = TOWN.location("coffee_shop_staff")

    assert sorted(s.id for s in bar) == ["bar-10-3", "bar-10-4", "bar-10-5", "bar-2-6", "bar-3-6"]
    stools = {(x, SpotKind.BAR, STOOL_M) for x in range(10, 15)}
    assert {(s.x, s.kind, s.dz) for s in bar} == stools
    assert {s.facing for s in bar} == {Facing.WEST}
    assert all(counter.entry.x < s.x for s in bar)
    assert pieces_at(10, FLOOR_ROW, "coffee_shop_floor_0") == {"bar_counter", "stool"}


def test_the_noodle_bars_stools_face_the_kitchen() -> None:
    stools = stools_at("noodle_bar_floor_0")
    kitchen = min(x for x in range(17) if "stove" in pieces_at(x, FLOOR_ROW, "noodle_bar_floor_0"))

    assert len(stools) == 5 and {s.facing for s in stools} == {Facing.EAST}
    assert all(s.x < kitchen for s in stools)


def facing_towards(x: int, there: float) -> Facing:
    return Facing.EAST if there > x else Facing.WEST


def test_the_squares_benches_face_the_fountain_and_the_gallerys_the_nearest_painting() -> None:
    square = [s for s in MAPS["high_street"].spots if s.kind is SpotKind.SEAT]
    [fountain] = [p for p in PLANS["high_street"].furniture if p.name == "fountain"]
    middle = fountain.area.x + fountain.area.width / 2

    assert len(square) == 8
    assert all(s.facing is facing_towards(s.x, middle) for s in square)
    for floor in floors_of("gallery"):
        paintings = [x for item in floor.interactables for x in (item.area.x, item.area.x + 1)]
        for seat in (s for s in floor.spots if s.kind is SpotKind.SEAT):
            nearest = min(paintings, key=lambda x: abs(x - seat.x))
            assert seat.facing is facing_towards(seat.x, nearest), seat.id


def test_someone_on_a_stool_at_the_daily_grinds_bar_sits_facing_the_counter() -> None:
    village = Village()
    [stool] = [s for s in MAPS["coffee_shop_floor_0"].spots if s.id == "bar-10-4"]
    village.movement.place("mei", MapTile(map=stool.map, x=stool.x, y=stool.y))
    village.world.loop.tick()

    assert village.movement.on_spot("mei") == stool
    assert village.movement.posture("mei") == (Pose.SITTING, Facing.WEST)


def test_streets_have_a_flight_of_stairs_and_a_ladder() -> None:
    climbable = {
        (town.id, town.climb(x, y))
        for town in STREETS
        for y in range(town.height)
        for x in range(town.width)
        if town.climb(x, y)
    }

    assert climbable == {
        ("banyan_row", DoorKind.STAIRS),
        ("lychee_lane", DoorKind.LADDER),
        ("rooftops", DoorKind.LADDER),
        ("metro", DoorKind.STAIRS),
        ("metro", DoorKind.LADDER),
        ("sewers", DoorKind.LADDER),
    }


def test_the_cafe_the_noodle_bar_and_home_have_a_plug_downstairs() -> None:
    plugs = {
        item.id: item
        for town in MAPS.values()
        if town.id != SEWERS
        for item in town.interactables
        if item.kind is InteractableKind.PLUG
    }

    assert set(plugs) == {"coffee_shop_plug", "maker_space_plug", "noodle_bar_plug", "metro_plug"}
    for building in ("coffee_shop", "maker_space", "noodle_bar"):
        item = plugs[f"{building}_plug"]
        [stand] = item.stand
        assert item.map == f"{building}_floor_0" and item.label == "Plug"
        assert MAPS[item.map].standing(stand.x, stand.y) and MAPS[item.map].lit(stand.x, stand.y)
    home = TOWN.location("maker_space")
    assert plugs["maker_space_plug"].stand == [home.entry], "they wake on it after collapsing"


def test_only_the_streets_under_the_village_are_underground_or_dark() -> None:
    for plan in village():
        dark = [light.id for light in plan.light if not light.lit]
        below = plan.id in UNDERGROUND or plan.properties.get("street") in UNDERGROUND
        assert plan.properties.get("underground", False) is (plan.id in UNDERGROUND), plan.id
        assert below or not dark, plan.id


def test_the_readme_names_every_street_building_room_and_piece_of_furniture() -> None:
    readme = (STREET_DIR / "README.md").read_text()
    plans = village()
    names = {plan.id for plan in plans if plan.kind is MapKind.STREET}
    names |= {facade.id for plan in plans for facade in plan.buildings}
    names |= {str(plan.properties["room"]) for plan in plans if plan.kind is MapKind.FLOOR}
    names |= {piece.name for plan in plans for piece in plan.furniture}
    names -= {f"house_{n}" for n in range(2, 10)}

    assert {name for name in names if f"`{name}`" not in readme} == set()


def test_every_map_has_the_layers_and_furniture_has_names() -> None:
    names = ["solid", "climbable", "collision", BUILDINGS_LAYER, FURNITURE_LAYER, "locations"]
    names += ["murals", "doors", "interactables", "spots", LIGHT_LAYER, PICKUPS_LAYER]
    furniture = set()
    for path in [*STREET_DIR.glob("*.tmj"), *(STREET_DIR / "floors").glob("*.tmj")]:
        data = json.loads(path.read_text())
        found = [layer["name"] for layer in data["layers"]]
        assert found in (names, [*names, CREATURES_LAYER]), path.name
        [layer] = [layer for layer in data["layers"] if layer["name"] == FURNITURE_LAYER]
        for piece in layer["objects"]:
            assert piece["name"] == piece["type"] and re.fullmatch(r"[a-z0-9_]+", piece["type"])
            furniture.add(piece["type"])
    assert {"cafe_table", "bench", "bed", "workbench", "fountain", "news_terminal"} <= furniture


def test_the_villages_farthest_two_places_are_less_than_a_minute_and_a_half_apart() -> None:
    below = {plan.id for plan in PLANS.values() if plan.properties.get("street") in UNDERGROUND}
    doors = door_ends(MAPS)
    entries = [
        Spot(loc.map, loc.entry.x, loc.entry.y)
        for loc in TOWN.locations
        if loc.map not in below | UNDERGROUND
    ]
    routes = [find_route(MAPS, a, b, doors) for a, b in itertools.combinations(entries, 2)]
    longest = max(route_length(route) for route in routes if route is not None)

    assert None not in routes

    assert 40 <= longest / WALKING_SPEED <= 90


class Village:
    def __init__(self) -> None:
        self.world = World(Clock(START), FakeWallClock())
        self.movement = Movement(MAPS, self.world.bus)
        self.world.loop.register(self.movement)
        self.moves: list[EntityMoved] = []
        self.world.bus.subscribe(EntityMoved, self.moves.append)

    def finish(self, walk: Walk, limit: float = 600) -> None:
        while not walk.done:
            assert (self.world.clock.now - START).total_seconds() < limit
            self.world.loop.tick()

    def fill(self, location_id: str, floor: int) -> None:
        """Someone on every spot on that floor of the location."""
        town = MAPS[f"{location_id}_floor_{floor}"]
        for i, spot in enumerate(town.spots):
            tile = MapTile(map=town.id, x=spot.x, y=spot.y)
            self.movement.place(f"{location_id}_{floor}_{i}", tile)

    def links_taken(self, entity: str) -> list[DoorKind]:
        doors = {
            (end.map, end.x, end.y): door
            for door in TOWN.doors
            for end in (door.outside, door.inside)
        }
        moves = [(m.map, round(m.x), round(m.y)) for m in self.moves if m.entity == entity]
        return [doors[a].kind for a, b in itertools.pairwise(moves) if a[0] != b[0]]


@pytest.mark.parametrize(
    ("location_id", "purpose", "full", "link_kind"),
    [
        ("coffee_shop", Purpose.DRINK, [0], DoorKind.STAIRS),
        ("gallery", Purpose.LOOK, [0, 1], DoorKind.LIFT),
        ("maker_space", Purpose.MAKE, [0, 1], DoorKind.LADDER),
    ],
)
def test_spots_on_upper_floors_are_found_and_reached_by_their_links(
    location_id: str, purpose: Purpose, full: list[int], link_kind: DoorKind
) -> None:
    village = Village()
    for floor in full:
        village.fill(location_id, floor)
    movement = village.movement
    movement.place("mei", "square")
    movement.intend("mei", purpose)

    walk = movement.walk_to("mei", location_id)
    village.finish(walk)

    here = movement.position("mei")
    spot = movement.on_spot("mei")
    assert walk.outcome is Outcome.ARRIVED
    assert MAPS[here.map].floor == max(full) + 1
    assert inside(TOWN.location(location_id), here)
    assert spot is not None and spot.map == here.map
    assert village.links_taken("mei")[-1] is link_kind


def test_someone_upstairs_is_in_the_building_and_stays_on_their_spot() -> None:
    village = Village()
    [spot] = [s for s in MAPS["coffee_shop_floor_1"].spots if s.id == "seat-11-3"]
    village.movement.place("mei", MapTile(map=spot.map, x=spot.x, y=spot.y))
    village.movement.intend("mei", Purpose.DRINK)

    walk = village.movement.walk_to("mei", "coffee_shop")

    assert inside(TOWN.location("coffee_shop"), village.movement.position("mei"))
    assert walk.outcome is Outcome.ARRIVED
    assert village.movement.on_spot("mei") == spot


def test_a_resident_can_stop_partway_up_the_lookout_ladder() -> None:
    village = Village()
    park = MAPS["lychee_lane"]
    ladder = [(x, y) for y in range(park.height) for x in range(park.width) if park.climb(x, y)]
    x, top = min(ladder, key=lambda cell: cell[1])
    village.movement.place("mei", MapTile(map=park.id, x=x - 3, y=GROUND))
    walk = village.movement.walk_to("mei", MapTile(map=park.id, x=x + 2, y=top))
    for _ in range(1000):
        if any((m.x, m.y) == (x, top + 1) for m in village.moves if m.entity == "mei"):
            break
        village.world.loop.tick()

    village.movement.stop("mei")
    for _ in range(50):
        village.world.loop.tick()

    here = village.movement.position("mei")
    assert walk.outcome is Outcome.CANCELLED
    assert here.x == x and top <= here.y <= top + 1
    assert park.climb(int(here.x), int(here.y)) is DoorKind.LADDER
