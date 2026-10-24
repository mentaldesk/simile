import asyncio
import json
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.app import create_app
from simile.economy.config import EconomyConfig
from simile.npc import load_npcs
from simile.persistence import investigation_of, player_of
from simile.schema import PLAYER_ID, Bionic, Body, DoorKind, InteractableKind, ItemKind
from simile.sim import Clock, World
from simile.story import make_incident
from simile.story.content import HATCH as HATCH_CLUE
from simile.story.incident import HATCH_LOG, LIFT_LOG
from simile.street.jump import GRADES, JUMP, OWN_JUMP, Jump, meets
from simile.street.plan import PICKUPS_LAYER, dumps, tmj
from simile.street.sewers import (
    APEX_ACTUATOR,
    HATCH,
    LANDING,
    LEVELS,
    SEWERS,
    SHAFT,
    back,
    reach,
    sewers,
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
JUMPS: dict[str, Jump] = {OWN_JUMP: JUMP, **{grade.value: jump for grade, jump in GRADES.items()}}
PRICES = EconomyConfig().salvage


def path_of(level: int) -> Path:
    return STREET_DIR / LEVELS_DIR / str(level) / f"{SEWERS}.tmj"


@dataclass(frozen=True)
class Played:
    town: TownMap
    reached: dict[str, frozenset[tuple[int, int]]]
    """Where the player's own legs and each grade get to from the landing."""
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
    reached = {name: frozenset(reach(town, START, jump)) for name, jump in JUMPS.items()}
    layers = json.loads(path.read_text())["layers"]
    [layer] = [each for each in layers if each["name"] == PICKUPS_LAYER]
    needs = {
        o["name"]: {p["name"]: p["value"] for p in o.get("properties", [])}.get("needs")
        for o in layer["objects"]
    }
    return Played(town, reached, needs)


@pytest.fixture(scope="module")
def level(tmp_path_factory: pytest.TempPathFactory) -> Callable[[int], Played]:
    folder = tmp_path_factory.mktemp("sewers")
    return lambda seed: played(seed, folder)


def ids(seed: int) -> str:
    return f"level {seed}" if seed < LEVELS else f"seed {seed}"


@pytest.mark.parametrize("seed", SEEDS, ids=ids)
def test_every_grade_of_legs_reaches_the_hatch_and_the_plugs_and_the_players_own_dont(
    seed: int, level: Callable[[int], Played]
) -> None:
    town, found = level(seed).town, level(seed).reached
    [hatch] = [item for item in town.interactables if item.id == HATCH]
    plugs = [item for item in town.interactables if item.kind is InteractableKind.PLUG]

    assert hatch.kind is InteractableKind.JACK and HATCH == HATCH_CLUE
    assert 1 <= len(plugs) <= 2
    for item in [hatch, *plugs]:
        [stand] = item.stand
        for grade in GRADES:
            assert (stand.x, stand.y) in found[grade.value], (item.id, grade)
    assert (hatch.stand[0].x, hatch.stand[0].y) not in found[OWN_JUMP], "it needs the legs"
    for item in plugs:
        assert town.lit(item.stand[0].x, item.stand[0].y), item.id


@pytest.mark.parametrize("seed", SEEDS, ids=ids)
def test_nobody_gets_stuck_on_any_grade_of_legs(seed: int, level: Callable[[int], Played]) -> None:
    town, found = level(seed).town, level(seed).reached

    for name, jump in JUMPS.items():
        cells = set(found[name])
        assert cells == back(town, cells, START, jump), name


@pytest.mark.parametrize("seed", SEEDS, ids=ids)
def test_each_pickup_is_in_reach_only_of_the_legs_it_needs(
    seed: int, level: Callable[[int], Played]
) -> None:
    town, found, recorded = level(seed).town, level(seed).reached, level(seed).needs

    for pickup in town.pickups:
        cell, needs = (pickup.x, pickup.y), recorded[pickup.id]
        for grade in GRADES:
            can = meets(GRADES[grade], needs or OWN_JUMP)
            assert (cell in found[grade.value]) is can, (pickup.id, needs, grade)
        if needs not in (None, OWN_JUMP):
            assert cell not in found[OWN_JUMP], pickup.id
        if pickup.kind is PickupKind.SECRET:
            assert needs is not None, f"{pickup.id} is a jump that walking doesn't reach"
    assert {Bionic.SPRING_LEGS.value, Bionic.SPRINT_LEGS.value} <= set(recorded.values())


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
    assert 0.4 < len(dark) / len(cells) < 0.95


def test_some_levels_hold_the_apex_actuator() -> None:
    holding = [
        number
        for number in range(LEVELS)
        if any(pickup.item == APEX_ACTUATOR for pickup in played(number).town.pickups)
    ]

    assert 2 <= len(holding) <= LEVELS - 2, holding


def test_every_grade_of_legs_finds_salvage_and_the_sprint_branch_finds_more() -> None:
    def worth(level: Played, grade: Bionic) -> float:
        return sum(
            PRICES[p.item.id]
            for p in level.town.pickups
            if p.kind is PickupKind.SALVAGE and p.item and (p.x, p.y) in level.reached[grade.value]
        )

    for number in range(LEVELS):
        level = played(number)
        assert 30 <= worth(level, Bionic.HYDRAULIC_LEGS) < worth(level, Bionic.SPRINT_LEGS)


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
