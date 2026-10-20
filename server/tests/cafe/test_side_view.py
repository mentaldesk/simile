from collections.abc import Mapping
from typing import Any

import pytest

from simile.behaviour import Activity, Goal
from simile.cafe.config import DEFAULT_CONFIG as CAFE_CONFIG
from simile.cafe.config import TODAY
from simile.cafe.events import Ordered, Served
from simile.schema import MapTile, Npc
from simile.sim import EntityMoved
from simile.world import Point
from simile.world.map import STREET_DIR, SpotKind, TownMap, load_maps

from .conftest import ANA, BEA, BEN, CAL, DAY, MAPS, Village, keen

pytestmark = pytest.mark.anyio

STREETS = load_maps(STREET_DIR)
GROUND = "coffee_shop_floor_0"
SIDE = CAFE_CONFIG.layouts[GROUND]
TILL = Point(3, 2, GROUND)
COFFEE = keen(Activity.COFFEE_SHOP)
CAREFUL = CAFE_CONFIG.model_copy(update={"mistake": 0.0})


def side_village(npcs: tuple[Npc, ...] = (BEA,), **kwargs: Any) -> Village:
    return Village(npcs, maps=STREETS, **kwargs)


def seat_spots(ground: str, maps: Mapping[str, TownMap]) -> list[str]:
    spots = [maps[s.map].spot_at(s.x, s.y) for s in CAFE_CONFIG.layouts[ground].seats]
    return [spot.id if spot and spot.kind is SpotKind.SEAT else "" for spot in spots]


@pytest.mark.parametrize(("ground", "maps"), [(TODAY, MAPS), (GROUND, STREETS)], ids=str)
def test_each_worlds_cafe_tiles_are_cells_to_stand_on_and_its_seats_are_seat_spots(
    ground: str, maps: Mapping[str, TownMap]
) -> None:
    layout = CAFE_CONFIG.layouts[ground]
    tiles = [layout.entrance, layout.machine, layout.hand_over, layout.pickup, layout.upstairs]

    assert {tile.map for tile in tiles} == {ground}
    assert all(maps[t.map].standing(t.x, t.y) for t in [*tiles, *layout.seats])
    assert seat_spots(ground, maps) == seat_spots(TODAY, MAPS)
    assert all(seat_spots(ground, maps))


def test_in_side_view_the_tables_are_upstairs_and_the_barista_rests_at_the_stairs() -> None:
    stairs = next(door for door in STREETS[GROUND].doors if door.id == "coffee_shop_stairs")

    assert {seat.map for seat in SIDE.seats} == {"coffee_shop_floor_1"}
    assert (stairs.outside.map, stairs.outside.x, stairs.outside.y) == (
        SIDE.upstairs.map,
        SIDE.upstairs.x,
        SIDE.upstairs.y,
    )


async def test_the_queue_runs_along_the_floor_away_from_the_counter() -> None:
    customers = ("ana", "ben", "cal")
    village = side_village((BEA, ANA, BEN, CAL), behaviour=COFFEE, config=CAREFUL)
    for n, npc in enumerate(customers):
        village.movement.place(npc, MapTile(map=GROUND, x=16 + n, y=2))
        village.behaviour.restore(npc, Goal(Activity.IDLE), {}, village.now, None, {})
    queued: set[tuple[str, float, float]] = set()

    def everyone_served() -> bool:
        for npc in village.cafe.queue:
            here = village.at(npc)
            if village.behaviour.minds[npc].walk is None:
                queued.add((here.map, here.x, here.y))
        return len(village.of(Served)) == len(customers)

    await village.run_until(everyone_served)

    assert [(spot.map, spot.x, spot.y) for spot in village.cafe.spots[:4]] == [
        (GROUND, x, 2) for x in (6, 7, 8, 9)
    ]
    assert all(STREETS[GROUND].standing(spot.x, spot.y) for spot in village.cafe.spots)
    assert queued == {(GROUND, x, 2) for x in (6, 7, 8)}
    assert [event.customer for event in village.of(Served)] == [
        event.customer for event in village.of(Ordered)
    ]


async def test_the_barista_takes_orders_at_the_till_and_makes_and_hands_over_beside_it() -> None:
    village = side_village((BEA, ANA), behaviour=COFFEE, config=CAREFUL)

    await village.run_until(lambda: bool(village.of(Served)))

    stood = [(m.map, m.x, m.y) for m in village.of(EntityMoved) if m.entity == "bea"]
    tiles = [TILL, SIDE.machine, SIDE.hand_over]
    assert village.cafe.till == MapTile(map=GROUND, x=3, y=2)
    assert all((tile.map, tile.x, tile.y) in stood for tile in tiles)


async def test_off_shift_the_barista_sleeps_at_the_foot_of_the_stairs() -> None:
    village = side_village(start=DAY.replace(hour=23, minute=30))

    await village.run(minutes=3)

    assert village.at("bea") == Point(SIDE.upstairs.x, SIDE.upstairs.y, GROUND)
    assert village.behaviour.goal("bea").activity is Activity.SLEEP
    assert not village.behaviour.minds["bea"].held


async def test_a_resident_who_was_just_served_climbs_to_a_table_upstairs() -> None:
    lingering = CAREFUL.model_copy(update={"sit": 1.0})
    village = side_village((BEA, ANA), behaviour=COFFEE, config=lingering)

    await village.run_until(lambda: bool(village.of(Served)))
    await village.run(minutes=45)

    here = village.at("ana")
    seats = {(seat.map, seat.x, seat.y) for seat in SIDE.seats}
    assert len(village.of(Served)) == 1
    assert (here.map, round(here.x), round(here.y)) in seats
