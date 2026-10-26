import asyncio
import json
import random
import time
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import cache
from itertools import combinations
from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.app import create_app
from simile.clinic.config import DEFAULT_CONFIG as CLINIC
from simile.economy.config import EconomyConfig
from simile.npc import load_npcs
from simile.persistence import investigation_of, player_of
from simile.schema import PLAYER_ID, Bionic, Body, DoorKind, InteractableKind, ItemKind
from simile.sim import Clock, World
from simile.story import make_incident
from simile.story.content import HATCH as HATCH_CLUE
from simile.story.incident import HATCH_LOG, LIFT_LOG
from simile.street.jump import FEET, JUMP, KITS, LEGS, OWN_JUMP, meets
from simile.street.moves import moves
from simile.street.plan import PICKUPS_LAYER, dumps, tmj
from simile.street.sewers import (
    APEX_ACTUATOR,
    CAVE,
    CAVE_SECRET,
    CEILING,
    DEN,
    DEN_SECRET,
    FLOORS,
    GAP,
    HATCH,
    LANDING,
    LEVELS,
    SECURITY_TERMINAL,
    SEWERS,
    SHAFT,
    WEIR,
    WEIR_AT,
    routes,
    sewers,
    stranded,
)
from simile.street.village import JUMPING, UNDERGROUND
from simile.world import Point, movement_of
from simile.world.map import LEVELS as LEVELS_DIR
from simile.world.map import (
    STREET_DIR,
    PickupKind,
    TownMap,
    level_count,
    level_of,
    load_map,
    load_maps,
    world_level,
)

MORE_SEEDS = range(LEVELS, LEVELS + 24)
"""Seeds past the committed levels', made afresh: the generator holds for any seed."""
SEEDS = [*range(LEVELS), *MORE_SEEDS]
START = (LANDING.x, LANDING.y)
FITTED = [name for name in KITS if name != OWN_JUMP]
PRICES = EconomyConfig().salvage
RECIPES = CLINIC.recipes


def path_of(level: int) -> Path:
    return STREET_DIR / LEVELS_DIR / str(level) / f"{SEWERS}.tmj"


@dataclass(frozen=True)
class Played:
    town: TownMap
    reached: dict[str, frozenset[tuple[int, int]]]
    """Where the player gets to from the landing on each of `KITS`, by its name."""
    stuck: dict[str, frozenset[tuple[int, int]]]
    """Where they get to on each and can't get back to the landing from."""
    needs: dict[str, str | None]
    """What each pickup records reaching it takes, by its id."""


@cache
def played(seed: int, folder: Path = Path()) -> Played:
    """A committed level, or a seed's made afresh into `folder`, read as the server reads it."""
    path = path_of(seed)
    if seed >= LEVELS:
        path = folder / str(seed) / f"{SEWERS}.tmj"
        path.parent.mkdir(parents=True)
        path.write_text(dumps(tmj(sewers(seed), "markers.png")))
    town = load_map(path)
    ways = {jump: routes(town, START, jump) for jump in set(KITS.values())}
    reached = {name: frozenset(ways[jump]) for name, jump in KITS.items()}
    stuck = {name: frozenset(stranded(ways[jump], START)) for name, jump in KITS.items()}
    layers = json.loads(path.read_text())["layers"]
    [layer] = [each for each in layers if each["name"] == PICKUPS_LAYER]
    needs = {
        o["name"]: {p["name"]: p["value"] for p in o.get("properties", [])}.get("needs")
        for o in layer["objects"]
    }
    return Played(town, reached, stuck, needs)


@pytest.fixture(scope="module")
def level(tmp_path_factory: pytest.TempPathFactory) -> Callable[[int], Played]:
    folder = tmp_path_factory.mktemp("sewers")
    return lambda seed: played(seed, folder)


def ids(seed: int) -> str:
    return f"level {seed}" if seed < LEVELS else f"seed {seed}"


@pytest.mark.parametrize("seed", SEEDS, ids=ids)
def test_the_legs_or_the_feet_reach_the_hatch_and_the_plugs_and_the_players_own_dont(
    seed: int, level: Callable[[int], Played]
) -> None:
    town, found = level(seed).town, level(seed).reached
    [hatch] = [item for item in town.interactables if item.id == HATCH]
    plugs = [item for item in town.interactables if item.kind is InteractableKind.PLUG]

    assert hatch.kind is InteractableKind.JACK and HATCH == HATCH_CLUE
    assert 1 <= len(plugs) <= 2
    for item in [hatch, *plugs]:
        [stand] = item.stand
        for name in FITTED:
            assert (stand.x, stand.y) in found[name], (item.id, name)
    assert (hatch.stand[0].x, hatch.stand[0].y) not in found[OWN_JUMP], "it needs the legs"
    for item in plugs:
        assert town.lit(item.stand[0].x, item.stand[0].y), item.id


@pytest.mark.parametrize("seed", SEEDS, ids=ids)
def test_nobody_gets_stuck_on_any_legs_or_feet(seed: int, level: Callable[[int], Played]) -> None:
    for name, stuck in level(seed).stuck.items():
        assert not stuck, name


@pytest.mark.parametrize("seed", SEEDS, ids=ids)
def test_each_pickup_is_in_reach_only_of_the_legs_or_feet_it_needs(
    seed: int, level: Callable[[int], Played]
) -> None:
    town, found, recorded = level(seed).town, level(seed).reached, level(seed).needs

    for pickup in town.pickups:
        cell, needs = (pickup.x, pickup.y), recorded[pickup.id]
        for name in FITTED:
            can = meets(KITS[name], needs or OWN_JUMP)
            assert (cell in found[name]) is can, (pickup.id, needs, name)
        if needs not in (None, OWN_JUMP):
            assert cell not in found[OWN_JUMP], pickup.id
        if pickup.kind is PickupKind.SECRET:
            assert needs is not None, f"{pickup.id} is a jump that walking doesn't reach"
    assert {Bionic.SPRING_FEET_2.value, Bionic.BIONIC_LEGS.value} <= set(recorded.values())


@pytest.mark.parametrize("seed", SEEDS, ids=ids)
def test_past_the_last_room_the_den_has_a_door_and_a_ladder_up_to_its_stash(
    seed: int, level: Callable[[int], Played]
) -> None:
    town, found = level(seed).town, level(seed).reached
    [door] = [light.area.x for light in town.light if light.id == "sewers_den"]
    ladder, floor, loft = door + DEN - 1, FLOORS[0], FLOORS[1]
    [stash] = [pickup for pickup in town.pickups if pickup.id == DEN_SECRET]

    assert town.walkable(door, floor) and all(town.solid(door, y) for y in range(CEILING, loft))
    assert all(town.climb(ladder, y) is DoorKind.LADDER for y in range(loft, floor))
    assert door < stash.x <= ladder and stash.y < loft and stash.money >= 90
    for name in FITTED:
        assert {(door + 1, floor), (stash.x, stash.y)} <= found[name], name
    assert (door, floor) not in found[OWN_JUMP]


@pytest.mark.parametrize("seed", SEEDS, ids=ids)
def test_past_the_den_the_bat_cave_climbs_three_dark_tiers_to_a_stash_only_the_legs_reach(
    seed: int, level: Callable[[int], Played]
) -> None:
    town, found = level(seed).town, level(seed).reached
    [door] = [light.area.x for light in town.light if light.id == "sewers_cave"]
    west, east = door + 1, door + CAVE
    [stash] = [pickup for pickup in town.pickups if pickup.id == CAVE_SECRET]

    assert east == town.width - 1 and town.walkable(door, FLOORS[0])
    assert all(town.solid(door, y) for y in range(CEILING, FLOORS[0] - 3))
    assert not any(town.lit(x, y) for x in range(door, east) for y in range(town.height))
    for tier, ladder in ((0, east - GAP - 3), (1, west + 1)):
        rungs = range(FLOORS[tier + 1], FLOORS[tier])
        assert all(town.climb(ladder, y) is DoorKind.LADDER for y in rungs)
    assert (stash.x, stash.y) == (east, FLOORS[2]) and stash.money >= 140
    needs = level(seed).needs[CAVE_SECRET]
    assert needs == Bionic.BIONIC_LEGS
    for name in FITTED:
        assert (west, FLOORS[0]) in found[name], name
        assert ((east, FLOORS[2]) in found[name]) == meets(KITS[name], needs), name


@pytest.mark.parametrize("seed", SEEDS, ids=ids)
def test_no_ladder_ends_where_holding_the_key_would_climb_on_to_the_next(
    seed: int, level: Callable[[int], Played]
) -> None:
    town = level(seed).town
    rungs = {(x, y) for y in range(town.height) for x in range(town.width) if town.climb(x, y)}
    tops = [(x, y) for x, y in rungs if (x, y - 1) not in rungs]
    ends = [(x, y, y + 1 + len(list(_run(rungs, x, y)))) for x, y in tops]

    for (x, top, foot), (other, other_top, other_foot) in combinations(ends, 2):
        if {top, foot} & {other_top, other_foot}:
            assert abs(x - other) >= 3, (x, other)


def _run(rungs: set[tuple[int, int]], x: int, y: int) -> Iterator[int]:
    while (x, y + 1) in rungs:
        y += 1
        yield y


@pytest.mark.parametrize("seed", SEEDS, ids=ids)
def test_every_salvage_names_an_item_the_buyers_price(
    seed: int, level: Callable[[int], Played]
) -> None:
    salvage = [p for p in level(seed).town.pickups if p.kind is PickupKind.SALVAGE]

    assert len(salvage) >= 6
    for pickup in salvage:
        assert pickup.item is not None and pickup.item.kind is ItemKind.SALVAGE, pickup.id
        assert pickup.item.id in PRICES, pickup.item.id


@pytest.mark.parametrize("seed", SEEDS, ids=ids)
def test_the_lift_lands_on_s8s_landing_which_is_lit_in_the_dark(
    seed: int, level: Callable[[int], Played]
) -> None:
    town = level(seed).town
    cells = [(x, y) for y in range(town.height) for x in range(town.width) if town.walkable(x, y)]

    [door] = town.doors
    assert (door.id, door.kind, door.inside) == ("metro_to_sewers", DoorKind.DOOR, LANDING)
    assert all(town.standing(x, LANDING.y) and town.lit(x, LANDING.y) for x in range(SHAFT))
    dark = [cell for cell in cells if not town.lit(*cell)]
    assert 0.3 < len(dark) / len(cells) < 0.95


@pytest.mark.parametrize("seed", SEEDS, ids=ids)
def test_every_level_holds_the_apex_actuator_past_the_gate_on_the_legs_and_on_the_feet(
    seed: int, level: Callable[[int], Played]
) -> None:
    played_level = level(seed)
    [actuator] = [p for p in played_level.town.pickups if p.item == APEX_ACTUATOR]
    cell, found = (actuator.x, actuator.y), played_level.reached

    assert played_level.needs[actuator.id] == OWN_JUMP
    assert cell in found[Bionic.BIONIC_LEGS.value] and cell in found[Bionic.SPRING_FEET.value]
    assert cell not in found[OWN_JUMP], "past the gate"


ZONE_RECIPES = (
    [Bionic.BIONIC_LEGS],
    [Bionic.SPRING_FEET, Bionic.INFRARED_EYE, Bionic.POWER_CELL_2],
)
"""What each zone teaches, in the order the player needs them: the legs before the gate, then the
feet past it, and the eye with the second cell, which it needs. The eye's lens is a villager's."""
VILLAGERS = Counter(RECIPES[Bionic.INFRARED_EYE].parts)


@pytest.mark.parametrize("seed", SEEDS, ids=ids)
def test_each_zone_teaches_its_recipes_and_holds_their_parts_where_youd_reach_them_by_then(
    seed: int, level: Callable[[int], Played]
) -> None:
    played_level = level(seed)
    town, found = played_level.town, played_level.reached
    weir = next(x for x in range(town.width) if town.standing(x, LANDING.y - WEIR))
    gate = weir - WEIR_AT
    finds = [item for item in town.interactables if item.items or item.teaches]
    by_zone = ([f for f in finds if f.area.x < gate], [f for f in finds if f.area.x > gate])

    for zone, recipes in enumerate(ZONE_RECIPES):
        assert [f.teaches for f in by_zone[zone] if f.teaches] == recipes, zone
        held = Counter(item.id for f in by_zone[zone] for item in f.items)
        needed = sum((Counter(RECIPES[bionic].parts) for bionic in recipes), Counter()) - VILLAGERS
        assert held >= needed, (zone, held, needed)
        for find in by_zone[zone]:
            cell = (find.stand[0].x, find.stand[0].y)
            assert all(cell in found[name] for name in FITTED), find.id
            assert (cell in found[OWN_JUMP]) is (zone == 0), find.id
    [terminal] = [f for f in finds if f.teaches is Bionic.INFRARED_EYE]
    assert terminal.id == SECURITY_TERMINAL and terminal.kind is InteractableKind.JACK
    assert {f.kind for f in finds} - {terminal.kind} == {InteractableKind.SEARCHABLE}


def test_the_feet_find_salvage_and_the_legs_find_more() -> None:
    def worth(level: Played, grade: Bionic) -> float:
        return sum(
            PRICES[p.item.id]
            for p in level.town.pickups
            if p.kind is PickupKind.SALVAGE and p.item and (p.x, p.y) in level.reached[grade.value]
        )

    for number in range(LEVELS):
        level = played(number)
        assert 30 <= worth(level, Bionic.SPRING_FEET) < worth(level, Bionic.BIONIC_LEGS)


@pytest.mark.parametrize("seed", SEEDS, ids=ids)
def test_the_legs_cross_the_gate_over_its_gap_and_the_feet_climb_its_weir(
    seed: int, level: Callable[[int], Played]
) -> None:
    town = level(seed).town
    weir = next(x for x in range(town.width) if town.standing(x, LANDING.y - WEIR))
    gate = weir - WEIR_AT
    walkway, over = (gate + 2, LANDING.y - 10), (gate + 3 + GAP, LANDING.y - 10)
    face, top = (weir - 1, LANDING.y), (weir, LANDING.y - WEIR)

    assert not any(town.walkable(x, walkway[1]) for x in range(walkway[0] + 1, over[0]))
    for name, jump in {OWN_JUMP: JUMP, **LEGS, **FEET}.items():
        assert (over in dict(moves(town, walkway, jump))) is (name in LEGS), name
        assert (top in dict(moves(town, face, jump))) is (name in FEET), name


def test_the_pool_is_the_size_the_worlds_levels_are_picked_from() -> None:
    folders = sorted(path.name for path in (STREET_DIR / LEVELS_DIR).iterdir() if path.is_dir())

    assert folders == sorted(str(n) for n in range(LEVELS)), "a level's folder came or went"
    assert level_count() == LEVELS, "a world's level is picked from them all: worlds would move"
    assert level_of(0, LEVELS) == 1, "today's village plays level 1"


def test_each_world_plays_one_of_the_committed_levels_by_its_seed() -> None:
    assert level_count() == LEVELS
    assert {level_of(seed, LEVELS) for seed in range(100)} == set(range(LEVELS))
    for number in range(LEVELS):
        assert load_maps(level=number)[SEWERS] == played(number).town
    assert SEWERS in JUMPING and SEWERS in UNDERGROUND


MakePackage = Callable[[dict[str, str]], str]
NOW = datetime(2026, 1, 1, 10, tzinfo=UTC)
LIFESPANS = ("behaviour", "economy", "memory", "protocol", "world")


def make_app(make_package: MakePackage) -> Starlette:
    files = {f"{m}/lifespan.py": f"from simile.{m}.lifespan import lifespan\n" for m in LIFESPANS}
    files["protocol/routes.py"] = "from simile.protocol.routes import routes\n"
    files["player/lifespan.py"] = "from simile.player.lifespan import running\n"
    app = create_app(make_package(files))
    app.state.world = World(Clock(NOW))
    return app


def next_of(ws: Any, kind: str) -> dict[str, Any]:
    for _ in range(500):
        if (message := ws.receive_json())["type"] == kind:
            return message
    raise AssertionError(f"no {kind}")


def move(client: TestClient, app: Starlette, ws: Any, x: float, y: float, map_id: str) -> None:
    ws.send_json({"type": "player_move", "position": {"x": x, "y": y, "map": map_id}})
    movement, deadline = movement_of(app), time.monotonic() + 2
    while client.portal.call(movement.entities).get(PLAYER_ID) != Point(x, y, map_id):
        assert time.monotonic() < deadline, "the server never had the player there"
        time.sleep(0.001)


def test_the_world_plays_its_level_and_its_hatch_holds_aris_trail(
    make_package: MakePackage,
) -> None:
    app = make_app(make_package)
    made = asyncio.run(make_incident(load_npcs(), NOW, None, rng=random.Random(1)))
    investigation_of(app).incident = made.incident
    player_of(app).body = Body(vertebra=Bionic.DATAJACK)
    number = world_level()
    [hatch] = [item for item in played(number).town.interactables if item.id == HATCH]
    [stand] = hatch.stand

    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        snapshot = next_of(ws, "snapshot")
        move(client, app, ws, 100, 15, "metro")
        move(client, app, ws, LANDING.x, LANDING.y, SEWERS)
        move(client, app, ws, stand.x, stand.y, SEWERS)
        ws.send_json({"type": "pick_up"})
        journal = next_of(ws, "journal")
        sewers_map = movement_of(app).maps[SEWERS]

    assert snapshot["level"] == number and sewers_map == played(number).town
    [entry] = journal["entries"]
    assert entry["fact_id"] == HATCH_LOG
    assert entry["source"] == {"kind": "clue", "id": HATCH, "name": "Maintenance hatch"}
    facts = {fact.id: fact for fact in made.incident.facts}
    assert [lead.fact_id for lead in facts[LIFT_LOG].leads] == [HATCH_LOG]
