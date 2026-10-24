import json
from collections import deque
from functools import cache
from typing import Any

import pytest

from simile.behaviour.scoring import Places
from simile.schema import Bionic, DoorKind, Facing, InteractableKind, LocationKind
from simile.street.jump import GRADES, JUMP, NEEDS, OWN_JUMP, Jump, meets
from simile.street.metro import (
    ALCOVE_SECRET,
    ARRIVAL,
    CLINIC,
    DEAD_TERMINAL,
    DOCTOR,
    ENTRANCE,
    GANTRY,
    GANTRY_SECRET,
    HIGH_LEDGE,
    LEDGE_SECRET,
    LEGS_ROWS,
    LIFT,
    LIFT_FOOT,
    METRO,
    PLUG,
    SCRAP_STALL,
    SCRAP_TRADER,
)
from simile.street.moves import moves
from simile.street.plan import LIGHT_LAYER, PICKUPS_LAYER
from simile.street.sewers import LANDING, SEWERS
from simile.street.village import GROUND, UNDERGROUND
from simile.world.map import STREET_DIR, SpotKind, load_maps, with_every_location
from simile.world.movement import Point, inside
from simile.world.paths import Spot, door_ends, find_route

MAPS = load_maps(STREET_DIR)
TOWN = with_every_location(MAPS)
METRO_MAP = MAPS[METRO]
CLINIC_FLOOR = f"{CLINIC}_floor_0"
BELOW = {METRO: METRO_MAP, CLINIC_FLOOR: MAPS[CLINIC_FLOOR], SEWERS: MAPS[SEWERS]}
START = Spot(METRO, ARRIVAL.x, ARRIVAL.y)


def objects(layer: str) -> list[dict[str, Any]]:
    data = json.loads((STREET_DIR / f"{METRO}.tmj").read_text())
    [found] = [each for each in data["layers"] if each["name"] == layer]
    return found["objects"]


def props(obj: dict[str, Any]) -> dict[str, Any]:
    return {p["name"]: p["value"] for p in obj.get("properties", [])}


def cell(obj: dict[str, Any]) -> tuple[int, int]:
    return obj["x"] // 16, obj["y"] // 16


def machine(item_id: str) -> Any:
    [item] = [item for item in METRO_MAP.interactables if item.id == item_id]
    return item


def stands(item_id: str) -> set[Spot]:
    return {Spot(METRO, tile.x, tile.y) for tile in machine(item_id).stand}


@cache
def reachable(jumps: bool | Jump) -> frozenset[Spot]:
    """Every cell under the village the player can get to from the top of the stairway."""
    doors = door_ends(BELOW)
    seen, queue = {START}, deque([START])
    while queue:
        here = queue.popleft()
        nexts = [Spot(here.map, *c) for c, _ in moves(BELOW[here.map], (here.x, here.y), jumps)]
        if here in doors:
            nexts.append(doors[here])
        for there in nexts:
            if there not in seen:
                seen.add(there)
                queue.append(there)
    return frozenset(seen)


def pickups(kind: str) -> dict[str, tuple[Spot, dict[str, Any]]]:
    return {
        o["name"]: (Spot(METRO, *cell(o)), props(o))
        for o in objects(PICKUPS_LAYER)
        if o["type"] == kind
    }


def roof() -> set[Spot]:
    """The top of the gantry's roof, which nobody stands on."""
    return {Spot(METRO, x, GANTRY - 5) for x in range(58, 74)}


def walkable() -> set[Spot]:
    return {
        Spot(town.id, x, y)
        for town in BELOW.values()
        for y in range(town.height)
        for x in range(town.width)
        if town.walkable(x, y)
    }


def test_a_stairway_goes_down_through_a_door_on_banyan_rows_promenade() -> None:
    [door] = [d for d in TOWN.doors if d.inside == ARRIVAL]

    assert door.id == "banyan_row_to_metro" and door.kind is DoorKind.DOOR
    assert (door.outside, door.inside) == (ENTRANCE, ARRIVAL)
    assert ENTRANCE.y > GROUND, "on the river promenade, below Banyan Row's street"
    assert ARRIVAL.y < GROUND
    top = max(x for x in range(METRO_MAP.width) if METRO_MAP.standing(x, ARRIVAL.y))
    assert METRO_MAP.climb(top + 1, ARRIVAL.y + 1) is DoorKind.STAIRS
    assert {METRO, SEWERS} == UNDERGROUND


def test_you_can_walk_down_through_the_metro_to_the_clinic_and_back() -> None:
    doors = door_ends(MAPS)
    promenade = Spot(ENTRANCE.map, ENTRANCE.x - 2, ENTRANCE.y)
    clinic = TOWN.location(CLINIC)
    inside = Spot(clinic.map, clinic.entry.x, clinic.entry.y)

    there = find_route(MAPS, promenade, inside, doors)
    back = find_route(MAPS, inside, promenade, doors)

    assert there is not None and back is not None
    assert {spot.map for spot in there} == {"banyan_row", METRO, CLINIC_FLOOR}
    assert any(METRO_MAP.climb(spot.x, spot.y) is DoorKind.STAIRS for spot in there)


def test_premium_legs_reach_every_cell_but_the_gantrys_roof() -> None:
    assert reachable(GRADES[Bionic.PREMIUM_LEGS]) == walkable() - roof()
    assert all(METRO_MAP.solid(spot.x, spot.y + 1) for spot in roof())


@pytest.mark.parametrize("needs", [None, *NEEDS], ids=lambda needs: needs or "walking")
def test_each_place_is_in_reach_only_with_what_it_records(needs: str | None) -> None:
    jump = NEEDS[needs] if needs else False
    reached = reachable(jump)

    for kind in ("salvage", "secret"):
        for name, (spot, held) in pickups(kind).items():
            recorded = held.get("needs")
            can = recorded is None or (jump is not False and meets(jump, recorded))
            assert (spot in reached) is can, (name, recorded)


def test_the_high_ledge_is_out_of_a_jump_and_in_the_hydraulic_legs_reach() -> None:
    ledge = machine(HIGH_LEDGE)
    row = ledge.stand[0].y
    under = {(t.x, y) for t in ledge.stand for y in range(row + 1, METRO_MAP.height)}
    floor = min(y for x, y in under if METRO_MAP.standing(x, y))
    hydraulic, sprint = GRADES[Bionic.HYDRAULIC_LEGS], GRADES[Bionic.SPRINT_LEGS]

    assert ledge.kind is InteractableKind.MACHINE
    assert floor - row == LEGS_ROWS > JUMP.rows == sprint.rows and sprint.rise < LEGS_ROWS
    assert hydraulic.rows > LEGS_ROWS
    assert stands(HIGH_LEDGE) <= reachable(hydraulic)
    assert not stands(HIGH_LEDGE) & reachable(GRADES[Bionic.BLADE_LEGS])


def test_the_gantry_is_a_gap_under_a_roof_that_only_a_sprint_clears() -> None:
    nook, edge = (63, GANTRY), (69, GANTRY)
    gap = range(nook[0] + 1, edge[0])

    assert len(gap) == 5 and not any(METRO_MAP.walkable(x, GANTRY) for x in gap)
    assert METRO_MAP.solid(edge[0], GANTRY - 4) and not METRO_MAP.solid(edge[0], GANTRY - 3)
    for grade, jump in GRADES.items():
        over = nook in dict(moves(METRO_MAP, edge, jump))
        assert over is (jump.run > JUMP.run), grade
    assert nook not in dict(moves(METRO_MAP, edge, True))


def test_the_spring_legs_reach_the_alcove_from_the_wall_below_it() -> None:
    alcove, held = pickups("secret")[ALCOVE_SECRET]
    wall = (82, 10)

    assert held["needs"] == Bionic.SPRING_LEGS and held["item"] == "ration_pack"
    assert wall[1] - alcove.y == 5
    assert (alcove.x, alcove.y) in dict(moves(METRO_MAP, wall, GRADES[Bionic.SPRING_LEGS]))
    assert (alcove.x, alcove.y) not in dict(moves(METRO_MAP, wall, GRADES[Bionic.HYDRAULIC_LEGS]))


def test_the_lift_and_the_dead_terminal_are_jacks_you_walk_up_to() -> None:
    walked = reachable(False)
    ends = {(end.map, end.x, end.y) for d in TOWN.doors for end in (d.outside, d.inside)}

    for item_id in (LIFT, DEAD_TERMINAL):
        assert machine(item_id).kind is InteractableKind.JACK
        assert stands(item_id) <= walked
    assert not {(s.map, s.x, s.y) for s in stands(DEAD_TERMINAL)} & ends
    assert stands(LIFT) == {Spot(METRO, LIFT_FOOT.x, LIFT_FOOT.y)}


def test_the_lift_goes_down_to_a_landing_in_the_sewers_and_back() -> None:
    [door] = [d for d in TOWN.doors if SEWERS in (d.outside.map, d.inside.map)]
    sewers = MAPS[SEWERS]

    data = json.loads((STREET_DIR / f"{SEWERS}.tmj").read_text())
    cells = {Spot(SEWERS, x, y) for y in range(sewers.height) for x in range(sewers.width)}

    assert (door.kind, door.outside, door.inside) == (DoorKind.DOOR, LIFT_FOOT, LANDING)
    assert props(data)["underground"] is True
    assert {cell for cell in cells if sewers.walkable(cell.x, cell.y)} <= reachable(False)
    assert sewers.light and all(light.lit for light in sewers.light)


def test_the_plug_is_in_a_lit_alcove_between_dark_stretches_of_tunnel() -> None:
    [plug] = stands(PLUG)
    lights = {o["name"]: (cell(o), o["width"] // 16, props(o)["lit"]) for o in objects(LIGHT_LAYER)}
    (x0, _), width, lit = lights["metro_maintenance"]

    assert machine(PLUG).kind is InteractableKind.PLUG
    assert plug in reachable(False)
    assert lit and x0 <= plug.x < x0 + width
    assert not lights["metro_tunnel_west"][2] and not lights["metro_tunnel_east"][2]
    assert not METRO_MAP.lit(plug.x - 2, plug.y) and not METRO_MAP.lit(plug.x + 2, plug.y)
    assert METRO_MAP.lit(plug.x, plug.y)


def test_the_metro_is_underground_and_lit_by_its_own_lights() -> None:
    data = json.loads((STREET_DIR / f"{METRO}.tmj").read_text())

    assert props(data)["underground"] is True
    assert {light.id for light in METRO_MAP.light if not light.lit} == {
        "metro_vault",
        "metro_tunnel_west",
        "metro_tunnel_east",
    }
    assert all(METRO_MAP.lit(x, GANTRY) for x in range(61, 74))


def test_the_light_areas_cover_every_cell_of_the_metro_once() -> None:
    covered: list[tuple[int, int]] = []
    for area in objects(LIGHT_LAYER):
        (x, y), w, h = cell(area), area["width"] // 16, area["height"] // 16
        assert area["type"] == "light" and isinstance(props(area)["lit"], bool)
        covered += [(cx, cy) for cy in range(y, y + h) for cx in range(x, x + w)]
    dark = {o["name"] for o in objects(LIGHT_LAYER) if not props(o)["lit"]}

    assert sorted(covered) == sorted(
        (x, y) for y in range(METRO_MAP.height) for x in range(METRO_MAP.width)
    )
    assert dark == {"metro_vault", "metro_tunnel_west", "metro_tunnel_east"}


def test_every_secret_needs_a_jump_and_holds_money_or_an_item() -> None:
    secrets = pickups("secret")

    assert len(secrets) == 5
    assert {held["needs"] for _, held in secrets.values()} == {
        OWN_JUMP,
        Bionic.HYDRAULIC_LEGS,
        Bionic.SPRING_LEGS,
        Bionic.SPRINT_LEGS,
    }
    for name, (spot, held) in secrets.items():
        assert spot not in reachable(False), name
        assert ("money" in held) != ("item" in held), name
        assert held.get("money", 1) > 0
    assert secrets[LEDGE_SECRET][0] in stands(HIGH_LEDGE)
    assert secrets[GANTRY_SECRET][1] == {"money": 60.0, "needs": Bionic.SPRINT_LEGS}


def test_salvage_lies_about_the_metro_and_two_pieces_wait_up_high() -> None:
    salvage = pickups("salvage")
    high = {name: held["needs"] for name, (_, held) in salvage.items() if held}

    assert len(salvage) == 6
    assert all(METRO_MAP.standing(spot.x, spot.y) for spot, _ in salvage.values())
    assert high == {"metro_salvage_4": Bionic.SPRING_LEGS, "metro_salvage_6": Bionic.HYDRAULIC_LEGS}
    assert salvage["metro_salvage_6"][0] in stands(HIGH_LEDGE)


def test_the_scrap_trader_and_the_doctor_have_stall_spots() -> None:
    [trader] = [s for s in METRO_MAP.spots if s.id == SCRAP_TRADER]
    [doctor] = MAPS[CLINIC_FLOOR].spots

    assert (trader.kind, trader.facing) == (SpotKind.STANDING, Facing.SOUTH)
    assert inside(TOWN.location(SCRAP_STALL), Point(trader.x, trader.y, METRO))
    assert doctor.id == DOCTOR and (doctor.kind, doctor.facing) == (trader.kind, trader.facing)
    walked = reachable(False)
    assert {Spot(METRO, trader.x, trader.y), Spot(CLINIC_FLOOR, doctor.x, doctor.y)} <= walked


def test_the_clinic_is_a_room_of_its_own_off_the_metro() -> None:
    clinic = TOWN.location(CLINIC)
    [door] = [d for d in TOWN.doors if d.id == CLINIC]

    assert clinic.kind is LocationKind.AMENITY and clinic.map == CLINIC_FLOOR
    assert MAPS[CLINIC_FLOOR].building == CLINIC and MAPS[CLINIC_FLOOR].floor == 0
    assert door.outside.map == METRO and door.inside.map == CLINIC_FLOOR


def test_no_resident_has_anywhere_to_go_in_the_metro() -> None:
    places = Places(TOWN)
    placed = {loc.map for locations in places.by_activity.values() for loc in locations}
    metro_ends = [end for d in TOWN.doors for end in (d.outside, d.inside) if end.map == METRO]

    assert {loc.id for loc in TOWN.locations if loc.map in BELOW} == {CLINIC, SCRAP_STALL}
    assert {loc.kind for loc in TOWN.locations if loc.map in BELOW} == {LocationKind.AMENITY}
    assert not placed & set(BELOW)
    assert len(metro_ends) == 3, "the stairway, the clinic's door and the lift: a dead end"


def test_the_hooks_keep_their_ids_and_cells() -> None:
    machines = {item.id: [(t.x, t.y) for t in item.stand] for item in METRO_MAP.interactables}
    pickups = {o["name"]: cell(o) for o in objects(PICKUPS_LAYER)}
    spots = {s.id: (s.map, s.x, s.y) for town in BELOW.values() for s in town.spots}

    assert machines == {
        PLUG: [(72, 15)],
        LIFT: [(100, 15)],
        DEAD_TERMINAL: [(104, 15)],
        HIGH_LEDGE: [(106, 12), (107, 12), (108, 12), (109, 12)],
    }
    assert spots == {SCRAP_TRADER: (METRO, 26, 15), DOCTOR: (CLINIC_FLOOR, 6, 2)}
    assert pickups == {
        "metro_secret_stairwell": (8, 7),
        "metro_salvage_1": (38, 12),
        "metro_secret_catwalk": (52, 10),
        "metro_salvage_2": (63, 15),
        "metro_salvage_3": (68, 15),
        "metro_salvage_4": (85, 5),
        "metro_secret_alcove": (86, 5),
        GANTRY_SECRET: (61, 8),
        "metro_salvage_5": (83, 15),
        "metro_salvage_6": (108, 12),
        LEDGE_SECRET: (106, 12),
    }
    assert (LIFT_FOOT.map, LIFT_FOOT.x, LIFT_FOOT.y) == (METRO, 100, 15)
