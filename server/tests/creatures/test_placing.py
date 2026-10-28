import heapq
import math
from collections import Counter
from itertools import combinations
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from simile.app import create_app
from simile.creatures.engine import Creature, Creatures, Sight, creatures_of
from simile.creatures.kinds import BOT
from simile.creatures.placing import populate, spawns
from simile.persistence import player_of
from simile.schema import CreatureKind, DoorKind, MapTile, Player, TileArea
from simile.sim import Clock, World, world_of
from simile.street.jump import JUMP
from simile.street.metro import ARRIVAL, METRO
from simile.street.moves import moves
from simile.street.plan import dumps, tmj
from simile.street.sewers import (
    BATS,
    BOT_FLOOR,
    CAVE_BATS,
    DEN,
    DEN_CLEAR,
    DEN_LADDER,
    DOGS,
    FLOORS,
    LANDING,
    LEVELS,
    RATS,
    REACH,
    SEWERS,
    SHAFT,
    Cells,
    routes,
    sewers,
)
from simile.world.map import STREET_DIR, PickupKind, TownMap, load_map, load_maps
from simile.world.movement import Point

from .test_lifespan import LIFESPANS, START, MakePackage, move

MORE_SEEDS = range(LEVELS, LEVELS + 8)
BOTS = range(3)
"""Up to one for each salvage before the gate, each on a floor of its own."""
WALK = 2.6
CLIMB = {DoorKind.LADDER: 1.0, DoorKind.STAIRS: 1.3}
"""The player's own pace, in tiles a second, as the client moves them."""
type Cell = tuple[int, int]


def walking(town: TownMap, start: Cell) -> dict[Cell, float]:
    """Seconds the player takes from `start` to each cell on their own legs, at their slowest."""
    found: dict[Cell, float] = {}
    frontier = [(0.0, start)]
    while frontier:
        spent, cell = heapq.heappop(frontier)
        if cell in found:
            continue
        found[cell] = spent
        for step in moves(town, cell, JUMP):
            kind = town.climb(*step.cell) or town.climb(*cell)
            pace = CLIMB.get(kind, WALK) if kind else WALK
            heapq.heappush(frontier, (spent + step.cost / pace, step.cell))
    return found


def race(maps: dict[str, TownMap], level: int, map_id: str, arrival: Cell) -> dict[str, float]:
    """When bots take each salvage, with the player waiting where they could have walked from."""
    town = maps[map_id]
    lying = {(p.x, p.y): p.id for p in town.pickups if p.kind is PickupKind.SALVAGE}
    taken: dict[str, float] = {}

    def collect(pickup: str) -> None:
        taken[pickup] = creatures.now
        del lying[next(cell for cell, id in lying.items() if id == pickup)]

    creatures = Creatures(
        maps,
        sense=lambda: Sight(Player(), Point(*arrival, map_id)),
        salvage=lambda here: lying if here.id == map_id else {},
        collect=collect,
    )
    placed = populate(creatures, spawns(level=level))
    bots = [c for c in placed if c.kind is BOT and c.map == map_id]
    reachable = {cell for c in bots for cell in lying if cost(c, cell) <= REACH}
    for _ in range(3000):
        creatures.tick(0.1)
    reach = walking(town, arrival)
    pickups = {p.id: (p.x, p.y) for p in town.pickups}
    late = {id: when for id, when in taken.items() if when <= reach[pickups[id]]}
    assert not late, f"bots beat a walking player to {late}"
    left = reachable & set(lying)
    assert not left, f"bots never took salvage they can get to at {left}"
    return taken


def stretch(creature: Creature) -> set[Cell]:
    """The floor a creature gets about, from where it starts."""
    found, queue = {creature.home}, [creature.home]
    while queue:
        for edge in creature.grid.edges(queue.pop()):
            if edge.to not in found:
                found.add(edge.to)
                queue.append(edge.to)
    return found


def cost(creature: Creature, cell: Cell) -> float:
    """What getting to `cell` costs `creature` from where it starts, by its own grid."""
    edges = creature.grid.path(creature.home, cell)
    reaches = (edges[-1].to if edges else creature.home) == cell
    return sum(edge.cost for edge in edges) if reaches else math.inf


def check(spawned: Creatures, zone_0: set[tuple[int, int]]) -> None:
    every = [c for c in spawned.all.values() if c.map == SEWERS]
    kinds = Counter(c.kind.id for c in every)
    bats = sum(BATS) + CAVE_BATS
    expected = {CreatureKind.RAT: sum(RATS), CreatureKind.DOG: DOGS, CreatureKind.BAT: bats}
    assert kinds[CreatureKind.BOT] in BOTS
    assert {kind: n for kind, n in kinds.items() if kind is not CreatureKind.BOT} == expected
    sewer = [c for c in every if c.kind.id in (CreatureKind.RAT, CreatureKind.BOT)]
    assert all(c.cell in zone_0 for c in sewer), "one is past the gate"
    town = spawned.maps[SEWERS]
    lights = {light.id: light.area for light in town.light}
    dogs = [c for c in every if c.kind.id is CreatureKind.DOG]
    kept = lights["sewers_den"].x + 1 + DEN_LADDER + DEN_CLEAR
    end = lights["sewers_den"].x + 1 + DEN
    den = TileArea(x=kept, y=FLOORS[0] - 3, width=end - kept, height=4)
    assert all(c.grid.area == den and c.cell not in zone_0 for c in dogs)
    floors = [stretch(c) for c in every if c.kind.id is CreatureKind.BOT]
    assert all(len(floor) >= BOT_FLOOR for floor in floors)
    assert all(not a & b for a, b in combinations(floors, 2)), "two bots share a floor"
    nests = {c.cell for c in every if c.kind.id is CreatureKind.RAT}
    assert not nests & set().union(*floors), "a nest is on a bot's floor"
    flying = [c for c in every if c.kind.id is CreatureKind.BAT]
    assert all(c.cell == c.roost and not town.lit(*c.cell) for c in flying), "one isn't roosting"
    cave = lights["sewers_cave"].x + 1
    in_cave = [c for c in flying if c.grid.area is not None and c.grid.area.x == cave]
    assert len(in_cave) == CAVE_BATS
    rooms = [c.grid.area for c in flying if c not in in_cave]
    floors = [{(x, a.y + 3) for x in range(a.x, a.x + a.width)} for a in rooms if a]
    assert all(floor & zone_0 for floor in floors), "one is past the gate"
    assert sorted(Counter((a.x, a.y) for a in rooms if a).values()) == sorted(BATS)
    assert all(c.home[0] >= SHAFT for c in sewer), "one is at the lift"
    rats = [c.grid.area for c in sewer if c.kind.id is CreatureKind.RAT]
    rooms = Counter((area.x, area.y) for area in rats if area is not None)
    assert sorted(rooms.values()) == sorted(RATS)


@pytest.mark.parametrize("level", range(LEVELS))
def test_every_level_places_its_creatures_where_they_keep_to(level: int) -> None:
    maps = load_maps(level=level)
    spawned = Creatures(maps)
    populate(spawned, spawns(level=level))
    zone_0 = set(routes(maps[SEWERS], (LANDING.x, LANDING.y), JUMP))
    check(spawned, zone_0)
    assert any(c.kind is BOT for c in spawned.all.values())


@pytest.mark.parametrize("seed", MORE_SEEDS)
def test_more_seeds_place_them_too(seed: int, tmp_path: Path) -> None:
    plan = sewers(seed)
    (tmp_path / f"{SEWERS}.tmj").write_text(dumps(tmj(plan, "markers.png")))
    town = load_map(tmp_path / f"{SEWERS}.tmj")
    spawned = Creatures({SEWERS: town})
    populate(spawned, spawns(tmp_path))
    check(spawned, set(routes(Cells(plan), (LANDING.x, LANDING.y), JUMP)))


def test_two_bots_guard_the_metro_s_platform_each_under_a_way_over_it() -> None:
    placed = [spawn for map_id, spawn in spawns(STREET_DIR) if map_id == "metro"]
    assert {spawn.kind for spawn in placed} == {CreatureKind.BOT}
    assert len(placed) == 2
    assert all(spawn.area is not None and spawn.area.height == 1 for spawn in placed)
    town = load_maps()[METRO]
    for spawn in placed:
        area = spawn.area
        assert area is not None
        xs = range(area.x, area.x + area.width)
        over = [x for x in xs if any(town.solid(x, y) for y in range(area.y - 5, area.y))]
        assert len(over) >= area.width - 1, f"{spawn.id} has nothing over it"
    assert race(load_maps(), 0, METRO, (ARRIVAL.x, ARRIVAL.y)) == {}, "they keep off the salvage"


@pytest.mark.parametrize("level", range(LEVELS))
def test_a_player_walking_from_the_lift_gets_to_zone_0_s_salvage_before_a_bot(level: int) -> None:
    race(load_maps(level=level), level, SEWERS, (LANDING.x, LANDING.y))


def test_the_server_places_them_and_a_bot_s_take_is_the_player_s_and_leaves_their_piles(
    make_package: MakePackage,
) -> None:
    files = {f"{m}/lifespan.py": f"from simile.{m}.lifespan import lifespan\n" for m in LIFESPANS}
    files["creatures/lifespan.py"] = "from simile.creatures.lifespan import lifespan, running\n"
    files["protocol/routes.py"] = "from simile.protocol.routes import routes\n"
    files["player/lifespan.py"] = "from simile.player.lifespan import running\n"
    app = create_app(make_package(files))
    app.state.world = World(Clock(START))

    with TestClient(app) as client:
        creatures = creatures_of(app)
        assert {"metro_bot_1", "metro_bot_2"} <= set(creatures.all)
        client.portal.call(lambda: creatures.spawn(BOT, MapTile(map=METRO, x=58, y=15)))
        player = player_of(app)
        with client.websocket_connect("/ws") as ws:
            move(client, app, ws, ARRIVAL.x, ARRIVAL.y, METRO)
            for _ in range(600):
                client.portal.call(world_of(app).loop.tick)
            assert "metro_salvage_2" in player.taken, "no bot took the platform's salvage"
            for _ in range(10_000):
                message = ws.receive_json()
                if message["type"] == "player_state":
                    piles = {(p["at"]["x"], p["at"]["y"]) for p in message["piles"]}
                    if (63, 15) not in piles:
                        break
            else:
                raise AssertionError("the client still sees it lying there")
