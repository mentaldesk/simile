from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.app import create_app
from simile.behaviour import Activity, behaviour_of
from simile.npc import load_npcs
from simile.protocol import EntityKind, Position, SnapshotMessage, hub_of
from simile.protocol.fixtures import fixture_world
from simile.schema import PLAYER_ID, MapTile
from simile.sim import STEP, Clock, World, world_of
from simile.world import movement_of
from simile.world.movement import inside

MakePackage = Callable[[dict[str, str]], str]

NPCS = load_npcs()
START = datetime(2026, 1, 1, 10, tzinfo=UTC)
CONVERSATION = fixture_world()[1][0]


@pytest.fixture
def app(make_package: MakePackage) -> Starlette:
    package = make_package(
        {
            f"{module}/lifespan.py": f"from simile.{module}.lifespan import lifespan\n"
            for module in ("behaviour", "memory", "protocol", "world")
        }
        | {"protocol/routes.py": "from simile.protocol.routes import routes\n"}
    )
    app = create_app(package)
    app.state.world = World(Clock(START))
    return app


def test_puts_every_npc_at_home(app: Starlette) -> None:
    with TestClient(app):
        movement = movement_of(app)
        for npc in NPCS:
            x, y = movement.position(npc.id)
            assert inside(movement.town.location(npc.home), (round(x), round(y)))


def test_decides_on_the_tick_loop(app: Starlette) -> None:
    with TestClient(app):
        behaviour = behaviour_of(app)
        for mind in behaviour.minds.values():
            mind.until = START
        for _ in range(round(behaviour.config.think_every / STEP)):
            world_of(app).loop.tick()

        goals = [behaviour.goal(npc.id).activity for npc in NPCS]
        assert any(goal is not Activity.HOME for goal in goals)


def test_clients_get_the_village_in_their_snapshot(app: Starlette) -> None:
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        snapshot = SnapshotMessage.model_validate(ws.receive_json())

    positions = movement_of(app).entities()
    npcs = [entity for entity in snapshot.entities if entity.kind is EntityKind.NPC]
    assert [(e.id, e.name) for e in npcs] == [(npc.id, npc.name) for npc in NPCS]
    assert all((e.position.x, e.position.y) == positions[e.id] for e in npcs)
    assert snapshot.map_id == "village"
    assert snapshot.conversations == []
    assert snapshot.time >= START


def test_the_snapshot_puts_a_resident_inside_on_the_interiors_map(app: Starlette) -> None:
    with TestClient(app):
        movement_of(app).place(NPCS[0].id, MapTile(map="coffee_shop", x=5, y=6))
        entity = next(e for e in hub_of(app).snapshot().entities if e.id == NPCS[0].id)

    assert entity.position == Position(x=5, y=6, map="coffee_shop")


def test_the_player_starts_in_the_square_then_is_where_they_moved(app: Starlette) -> None:
    with TestClient(app):
        hub = hub_of(app)
        square = movement_of(app).town.location("square").entry

        def player() -> tuple[float, float]:
            entity = next(e for e in hub.snapshot().entities if e.id == PLAYER_ID)
            assert entity.kind is EntityKind.PLAYER
            return entity.position.x, entity.position.y

        assert player() == (square.x, square.y)
        hub.receive('{"type": "player_move", "position": {"x": 14, "y": 12.5}}')
        assert player() == (14, 12.5)


def test_conversations_in_the_snapshot_come_from_the_hook(app: Starlette) -> None:
    with TestClient(app):
        behaviour_of(app).hooks.set(conversations=lambda: [CONVERSATION])

        assert hub_of(app).snapshot().conversations == [CONVERSATION]


def test_stops_on_shutdown(app: Starlette) -> None:
    with TestClient(app):
        behaviour = behaviour_of(app)
        hub = hub_of(app)
    for mind in behaviour.minds.values():
        mind.until = START

    for _ in range(round(behaviour.config.think_every / STEP)):
        world_of(app).loop.tick()

    assert all(mind.walk is None for mind in behaviour.minds.values())
    assert hub.snapshot().entities == fixture_world()[0]
