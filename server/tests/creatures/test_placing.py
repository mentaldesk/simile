import heapq
from collections import Counter
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from simile.app import create_app
from simile.creatures.engine import Creatures, Sight, creatures_of
from simile.creatures.placing import populate, spawns
from simile.persistence import player_of
from simile.schema import CreatureKind, DoorKind, Player
from simile.sim import Clock, World, world_of
from simile.street.jump import JUMP
from simile.street.metro import ARRIVAL, METRO
from simile.street.moves import moves
from simile.street.plan import dumps, tmj
from simile.street.sewers import LANDING, LEVELS, RATS, SEWERS, SHAFT, Cells, routes, sewers
from simile.world.map import STREET_DIR, PickupKind, TownMap, load_map, load_maps
from simile.world.movement import Point

from .test_lifespan import LIFESPANS, START, MakePackage, move

MORE_SEEDS = range(LEVELS, LEVELS + 8)
BOTS = 2
"""One for each salvage before the gate."""
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
    """When the bots take each salvage on the map, with the player standing where they arrive,
    checked to be after the player could have walked there."""
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
    populate(creatures, spawns(level=level))
    for _ in range(1200):
        creatures.tick(0.1)
    reach = walking(town, arrival)
    pickups = {p.id: (p.x, p.y) for p in town.pickups}
    late = {id: when for id, when in taken.items() if when <= reach[pickups[id]]}
    assert not late, f"bots beat a walking player to {late}"
    return taken


def check(spawned: Creatures, zone_0: set[tuple[int, int]]) -> None:
    sewer = [c for c in spawned.all.values() if c.map == SEWERS]
    kinds = Counter(c.kind.id for c in sewer)
    assert kinds == {CreatureKind.RAT: sum(RATS), CreatureKind.BOT: BOTS}
    assert all(c.cell in zone_0 for c in sewer), "one is past the gate"
    assert all(c.home[0] >= SHAFT for c in sewer), "one is at the lift"
    rats = [c.grid.area for c in sewer if c.kind.id is CreatureKind.RAT]
    rooms = Counter((area.x, area.y) for area in rats if area is not None)
    assert sorted(rooms.values()) == sorted(RATS)


@pytest.mark.parametrize("level", range(LEVELS))
def test_every_level_places_its_rats_and_bots_before_the_gate(level: int) -> None:
    maps = load_maps(level=level)
    spawned = Creatures(maps)
    populate(spawned, spawns(level=level))
    zone_0 = set(routes(maps[SEWERS], (LANDING.x, LANDING.y), JUMP))
    check(spawned, zone_0)


@pytest.mark.parametrize("seed", MORE_SEEDS)
def test_more_seeds_place_them_too(seed: int, tmp_path: Path) -> None:
    plan = sewers(seed)
    (tmp_path / f"{SEWERS}.tmj").write_text(dumps(tmj(plan, "markers.png")))
    town = load_map(tmp_path / f"{SEWERS}.tmj")
    spawned = Creatures({SEWERS: town})
    populate(spawned, spawns(tmp_path))
    check(spawned, set(routes(Cells(plan), (LANDING.x, LANDING.y), JUMP)))


def test_a_few_bots_work_the_metro_s_floor() -> None:
    placed = [spawn for map_id, spawn in spawns(STREET_DIR) if map_id == "metro"]
    assert {spawn.kind for spawn in placed} == {CreatureKind.BOT}
    assert len(placed) == 2
    assert all(spawn.area is not None and spawn.area.height == 1 for spawn in placed)


def test_a_player_walking_from_the_metro_s_stairs_gets_to_its_salvage_before_a_bot() -> None:
    taken = race(load_maps(), 0, METRO, (ARRIVAL.x, ARRIVAL.y))
    assert "metro_salvage_2" in taken, "the bots never take any"


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
        assert {"metro_bot_1", "metro_bot_2"} <= set(creatures_of(app).all)
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
