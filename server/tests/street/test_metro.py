import json
from collections import Counter, deque
from functools import cache
from typing import Any

import pytest

from simile.behaviour.scoring import Places
from simile.clinic.config import DEFAULT_CONFIG as CLINIC_CONFIG
from simile.economy.config import DEFAULT_CONFIG as ECONOMY
from simile.player.config import SALVAGE
from simile.schema import Bionic, DoorKind, Facing, InteractableKind, LocationKind
from simile.street.finds import COPPER_WIRE
from simile.street.jump import FEET, JUMP, KITS, LEGS, OWN_JUMP, Jump, meets
from simile.street.metro import (
    ALCOVE_SECRET,
    ARRIVAL,
    CLINIC,
    CONTAINER,
    CRANE,
    CRANE_SECRET,
    DEAD_TERMINAL,
    DECK,
    DEPOT_END,
    DOCTOR,
    ENTRANCE,
    FREIGHT_CRATES,
    FRIDGE,
    GANTRY,
    GANTRY_SECRET,
    HIGH_LEDGE,
    LEDGE_ROWS,
    LEDGE_SECRET,
    LIFT,
    LIFT_FOOT,
    LOCKERS,
    METRO,
    MEZZANINE,
    PLUG,
    RELAY_RACK,
    SCRAP_STALL,
    SCRAP_TRADER,
    SIGNAL_DESK,
    STACK,
    STORE_SECRET,
    STORE_WALL,
    SWITCHBOARD,
    TICKET_MACHINE,
    TOOL_CRATE,
)
from simile.street.moves import moves
from simile.street.plan import LIGHT_LAYER, PICKUPS_LAYER
from simile.street.sewers import LANDING, SEWERS
from simile.street.village import GROUND, UNDERGROUND
from simile.world.map import STREET_DIR, PickupKind, SpotKind, load_maps, with_every_location
from simile.world.movement import Point, inside
from simile.world.paths import Spot, door_ends, find_route

MAPS = load_maps(STREET_DIR)
TOWN = with_every_location(MAPS)
METRO_MAP = MAPS[METRO]
CLINIC_FLOOR = f"{CLINIC}_floor_0"
BELOW = {METRO: METRO_MAP, CLINIC_FLOOR: MAPS[CLINIC_FLOOR], SEWERS: MAPS[SEWERS]}
START = Spot(METRO, ARRIVAL.x, ARRIVAL.y)
CLINIC_RECIPES = CLINIC_CONFIG.recipes


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
    """The tops of the gantry's roof and the shed's, which nobody stands on."""
    gantry = {Spot(METRO, x, GANTRY - 5) for x in range(58, 74)}
    return gantry | {Spot(METRO, x, MEZZANINE - 5) for x in range(205, METRO_MAP.width)}


def walkable() -> set[Spot]:
    return {
        Spot(town.id, x, y)
        for town in BELOW.values()
        if town.id != SEWERS
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
    top = max(x for x in range(20) if METRO_MAP.standing(x, ARRIVAL.y))
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


@pytest.mark.parametrize("kit", ["bionic_legs_2+spring_feet_2"])
def test_the_legs_and_feet_together_reach_every_cell_but_the_gantrys_roof(kit: str) -> None:
    reached = {spot for spot in reachable(KITS[kit]) if spot.map != SEWERS}
    assert reached == walkable() - roof()
    assert all(METRO_MAP.solid(spot.x, spot.y + 1) for spot in roof())


@pytest.mark.parametrize("kit", [None, *KITS], ids=lambda kit: kit or "walking")
def test_each_place_is_in_reach_only_with_what_it_records(kit: str | None) -> None:
    jump = KITS[kit] if kit else False
    reached = reachable(jump)

    for kind in ("salvage", "secret"):
        for name, (spot, held) in pickups(kind).items():
            recorded = held.get("needs")
            can = recorded is None or (jump is not False and meets(jump, recorded))
            assert (spot in reached) is can, (name, recorded)


def test_the_high_ledge_is_reached_with_the_feet_and_not_on_the_legs_alone() -> None:
    ledge = machine(HIGH_LEDGE)
    row = ledge.stand[0].y
    under = {(t.x, y) for t in ledge.stand for y in range(row + 1, METRO_MAP.height)}
    floor = min(y for x, y in under if METRO_MAP.standing(x, y))
    feet = FEET[Bionic.SPRING_FEET]

    assert ledge.kind is InteractableKind.MACHINE
    assert floor - row == LEDGE_ROWS > JUMP.rows and feet.rows > LEDGE_ROWS
    for grade, jump in {**LEGS, **FEET}.items():
        assert bool(stands(HIGH_LEDGE) & reachable(jump)) is (grade in FEET), grade


def test_the_gantry_is_a_gap_under_a_roof_that_only_the_legs_clear() -> None:
    nook, edge = (63, GANTRY), (69, GANTRY)
    gap = range(nook[0] + 1, edge[0])

    assert len(gap) == 5 and not any(METRO_MAP.walkable(x, GANTRY) for x in gap)
    assert METRO_MAP.solid(edge[0], GANTRY - 4) and not METRO_MAP.solid(edge[0], GANTRY - 3)
    for kit, jump in KITS.items():
        over = nook in dict(moves(METRO_MAP, edge, jump))
        assert over is (jump.run > JUMP.run), kit
    assert nook not in dict(moves(METRO_MAP, edge, True))


def test_the_second_grade_of_feet_reaches_the_alcove_from_the_wall_below_it() -> None:
    alcove, held = pickups("secret")[ALCOVE_SECRET]
    wall = (82, 10)

    assert held["needs"] == Bionic.SPRING_FEET_2 and held["item"] == "ration_pack"
    assert wall[1] - alcove.y == 5
    assert (alcove.x, alcove.y) in dict(moves(METRO_MAP, wall, FEET[Bionic.SPRING_FEET_2]))
    assert (alcove.x, alcove.y) not in dict(moves(METRO_MAP, wall, FEET[Bionic.SPRING_FEET]))


def test_the_cell_and_the_datajack_are_found_at_home_and_on_the_metro_on_foot() -> None:
    def held(maps: list[str]) -> Counter[str]:
        things = [
            thing
            for map_id in maps
            for thing in MAPS[map_id].interactables
            if map_id != METRO or thing.area.x < DEPOT_END
        ]
        return Counter(item.id for thing in things for item in thing.items)

    home = [f"maker_space_floor_{n}" for n in range(3)]
    [bench] = [t for t in MAPS[home[0]].interactables if t.teaches is not None]
    needed = Counter(CLINIC_RECIPES[Bionic.POWER_CELL].parts)
    needed += Counter(CLINIC_RECIPES[Bionic.DATAJACK].parts)
    walking = reachable(False)

    assert (bench.label, bench.kind, bench.teaches) == (
        "Aris's bench",
        InteractableKind.SEARCHABLE,
        Bionic.DATAJACK,
    )
    assert held(home) == {
        "lithium_cell": 1,
        "charge_controller": 1,
        "usb_c_connector": 1,
        "copper_wire": 1,
    }
    assert held([METRO]) == {"lithium_cell": 2, "copper_wire": 2}
    assert held(home) + held([METRO]) == needed
    for find in (machine(TICKET_MACHINE), machine(FRIDGE)):
        assert find.kind is InteractableKind.SEARCHABLE
        assert all(Spot(METRO, t.x, t.y) in walking for t in find.stand), find.id
    assert SALVAGE["metro_salvage_1"].item == COPPER_WIRE


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

    data = json.loads((STREET_DIR / "levels" / "0" / f"{SEWERS}.tmj").read_text())
    landing = {Spot(SEWERS, x, GROUND) for x in range(12)}

    assert (door.kind, door.outside, door.inside) == (DoorKind.DOOR, LIFT_FOOT, LANDING)
    assert props(data)["underground"] is True
    assert landing <= reachable(False)
    assert all(sewers.lit(cell.x, cell.y) for cell in landing)


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


DARK = {
    "metro_vault",
    "metro_tunnel_west",
    "metro_tunnel_east",
    "metro_siding",
    "metro_track",
}


def test_the_metro_is_underground_and_lit_by_its_own_lights() -> None:
    data = json.loads((STREET_DIR / f"{METRO}.tmj").read_text())

    assert props(data)["underground"] is True
    assert {light.id for light in METRO_MAP.light if not light.lit} == DARK
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
    assert dark == DARK


def test_every_secret_needs_a_jump_and_holds_money_or_an_item() -> None:
    secrets = pickups("secret")

    assert len(secrets) == 9
    assert {held["needs"] for _, held in secrets.values()} == {
        OWN_JUMP,
        Bionic.SPRING_FEET,
        Bionic.SPRING_FEET_2,
        Bionic.BIONIC_LEGS,
    }
    for name, (spot, held) in secrets.items():
        assert spot not in reachable(False), name
        assert ("money" in held) != ("item" in held), name
        assert held.get("money", 1) > 0
    assert secrets[LEDGE_SECRET][0] in stands(HIGH_LEDGE)
    assert secrets[GANTRY_SECRET][1] == {"money": 60.0, "needs": Bionic.BIONIC_LEGS}


def test_salvage_lies_about_the_metro_and_four_pieces_wait_up_high() -> None:
    salvage = pickups("salvage")
    high = {name: held["needs"] for name, (_, held) in salvage.items() if "needs" in held}

    assert len(salvage) == 11
    assert all(METRO_MAP.standing(spot.x, spot.y) for spot, _ in salvage.values())
    assert high == {
        "metro_salvage_4": Bionic.SPRING_FEET_2,
        "metro_salvage_6": Bionic.SPRING_FEET,
        "metro_salvage_10": Bionic.SPRING_FEET,
        "metro_salvage_11": Bionic.BIONIC_LEGS,
    }
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
        TICKET_MACHINE: [(15, 12)],
        FRIDGE: [(70, 15)],
        FREIGHT_CRATES: [(119, 15)],
        CONTAINER: [(x, 15) for x in range(124, 130)],
        SWITCHBOARD: [(143, 11), (144, 11)],
        RELAY_RACK: [(146, 11), (147, 11)],
        SIGNAL_DESK: [(150, 11)],
        TOOL_CRATE: [(168, 15)],
        LOCKERS: [(210, 15), (211, 15)],
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
        "metro_secret_container": (135, 12),
        CRANE_SECRET: (132, 5),
        "metro_salvage_10": (137, 5),
        "metro_salvage_7": (139, 15),
        "metro_salvage_8": (152, 11),
        "metro_salvage_9": (174, 15),
        "metro_secret_tunnel": (195, 10),
        "metro_salvage_11": (224, 15),
        STORE_SECRET: (228, 15),
    }
    assert (LIFT_FOOT.map, LIFT_FOOT.x, LIFT_FOOT.y) == (METRO, 100, 15)


BEYOND = (SWITCHBOARD, RELAY_RACK, CONTAINER, FREIGHT_CRATES, TOOL_CRATE, LOCKERS)


def walk(start: tuple[int, int]) -> set[tuple[int, int]]:
    """Every metro cell walking and climbing get to from `start`, without a jump."""
    seen, queue = {start}, deque([start])
    while queue:
        for there, _ in moves(METRO_MAP, queue.popleft(), False):
            if there not in seen:
                seen.add(there)
                queue.append(there)
    return seen


def test_the_metro_goes_on_past_the_clinic_and_its_new_places_are_walked_to_from_there() -> None:
    clinic = next(d.outside for d in TOWN.doors if d.id == CLINIC)
    walked = walk((clinic.x, clinic.y))
    things = [*BEYOND, SIGNAL_DESK]
    salvage = [(s.x, s.y) for s, held in pickups("salvage").values() if "needs" not in held]

    assert METRO_MAP.width > DEPOT_END
    assert all(machine(thing).area.x >= DEPOT_END for thing in things)
    for thing in things:
        assert {(t.x, t.y) for t in machine(thing).stand} <= walked, thing
    assert set(salvage) <= walked
    assert (STORE_WALL - 1, GROUND) in walked and (STORE_WALL + 3, GROUND) not in walked


def test_the_siding_stacks_containers_under_a_crane_that_only_the_feet_reach() -> None:
    top = GROUND - 6
    crane, _ = pickups("secret")[CRANE_SECRET]
    roof, held = pickups("secret")["metro_secret_container"]
    walked = reachable(False)

    assert all(Spot(METRO, x, top) in walked for x in range(STACK, STACK + 6))
    assert METRO_MAP.climb(STACK - 1, top) is DoorKind.LADDER
    assert top - CRANE == 4 and crane.y == CRANE
    assert held["needs"] == OWN_JUMP and roof not in walked and roof in reachable(True)
    for kit, jump in KITS.items():
        assert (crane in reachable(jump)) is (jump.rise > JUMP.rise), kit


def test_the_signal_box_is_a_deck_up_a_ladder_with_switchboards_to_strip_and_a_jack() -> None:
    walked = reachable(False)
    stripped = Counter(item.id for t in (SWITCHBOARD, RELAY_RACK) for item in machine(t).items)

    assert METRO_MAP.climb(141, DECK) is DoorKind.LADDER
    for thing in (SWITCHBOARD, RELAY_RACK, SIGNAL_DESK):
        assert {t.y for t in machine(thing).stand} == {DECK}
        assert stands(thing) <= walked, thing
    assert stripped == {"copper_wire": 2, "signal_relay": 1, "usb_c_connector": 1}
    assert machine(SIGNAL_DESK).kind is InteractableKind.JACK and machine(SIGNAL_DESK).items


def test_past_the_depot_it_is_dark_to_a_lit_shed_with_no_plug_at_the_end() -> None:
    plugs = [item.id for item in METRO_MAP.interactables if item.kind is InteractableKind.PLUG]

    assert plugs == [PLUG]
    assert not any(METRO_MAP.lit(x, GROUND) for x in range(DEPOT_END, 206))
    assert all(METRO_MAP.lit(x, GROUND) for x in range(206, METRO_MAP.width))


def test_the_store_room_is_behind_a_jammed_door_and_only_the_legs_clear_the_gap_over_it() -> None:
    edge, wall = (212, MEZZANINE), (STORE_WALL, MEZZANINE)
    gap = range(edge[0] + 1, wall[0])
    store = Spot(METRO, STORE_WALL + 4, GROUND)
    jams = [(STORE_WALL + dx, y) for dx in range(3) for y in range(MEZZANINE + 1, GROUND + 1)]

    assert all(METRO_MAP.solid(x, y) for x, y in jams)
    assert len(gap) == 5 and not any(METRO_MAP.walkable(x, MEZZANINE) for x in gap)
    assert METRO_MAP.solid(edge[0], MEZZANINE - 4) and not METRO_MAP.solid(edge[0], MEZZANINE - 3)
    assert METRO_MAP.climb(STORE_WALL + 3, MEZZANINE) is DoorKind.LADDER, "no way out"
    assert wall not in dict(moves(METRO_MAP, edge, True))
    for kit, jump in KITS.items():
        legs = jump.run > JUMP.run
        assert (wall in dict(moves(METRO_MAP, edge, jump))) is legs, kit
        assert (store in reachable(jump)) is legs, kit
    assert store not in reachable(True)
    assert pickups("secret")[STORE_SECRET][1] == {"money": 50.0, "needs": Bionic.BIONIC_LEGS}


def test_every_salvage_on_the_metro_has_a_price() -> None:
    for pickup in METRO_MAP.pickups:
        if pickup.kind is PickupKind.SALVAGE:
            item = pickup.item or SALVAGE[pickup.id].item
            assert item.id in ECONOMY.salvage, pickup.id
