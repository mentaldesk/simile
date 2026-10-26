from collections import Counter
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from simile.app import create_app
from simile.creatures.engine import Creatures, creatures_of
from simile.creatures.placing import populate, spawns
from simile.persistence import player_of
from simile.schema import CreatureKind
from simile.sim import Clock, World, world_of
from simile.street.jump import JUMP
from simile.street.plan import dumps, tmj
from simile.street.sewers import LANDING, LEVELS, RATS, SEWERS, SHAFT, Cells, routes, sewers
from simile.world.map import STREET_DIR, load_map, load_maps

from .test_lifespan import LIFESPANS, START, MakePackage, move, next_of

MORE_SEEDS = range(LEVELS, LEVELS + 8)
BOTS = 2
"""One in the room of each salvage before the gate."""


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


def test_the_server_places_them_and_a_bot_takes_metro_salvage_until_it_lies_there_again(
    make_package: MakePackage,
) -> None:
    files = {f"{m}/lifespan.py": f"from simile.{m}.lifespan import lifespan\n" for m in LIFESPANS}
    files["creatures/lifespan.py"] = "from simile.creatures.lifespan import lifespan, running\n"
    files["protocol/routes.py"] = "from simile.protocol.routes import routes\n"
    files["player/lifespan.py"] = "from simile.player.lifespan import running\n"
    app = create_app(make_package(files))
    app.state.world = World(Clock(START))

    salvage = {"metro_salvage_2": (63, 15), "metro_salvage_3": (68, 15)}
    with TestClient(app) as client:
        assert {"metro_bot_1", "metro_bot_2"} <= set(creatures_of(app).all)
        player = player_of(app)
        with client.websocket_connect("/ws") as ws:
            move(client, app, ws, 2, 9, "metro")
            for _ in range(200):
                client.portal.call(world_of(app).loop.tick)
            taken = set(salvage) & set(player.taken)
            assert taken, "no bot took the tunnel's salvage"
            gone = {salvage[pickup] for pickup in taken}
            for _ in range(500):
                state = next_of(ws, "player_state")
                if not gone & {(p["at"]["x"], p["at"]["y"]) for p in state["piles"]}:
                    break
            else:
                raise AssertionError("the client still sees it lying there")
