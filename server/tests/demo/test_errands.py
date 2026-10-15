from datetime import UTC, datetime

from simile.demo.errands import Errands
from simile.protocol import Position
from simile.protocol.fixtures import fixture_snapshot
from simile.sim import STEP, EntityMoved, EventBus
from simile.world import Movement
from simile.world.map import load_map

TOWN = load_map()
SNAPSHOT = fixture_snapshot(datetime(2026, 3, 14, 9, tzinfo=UTC))
NPCS = {e.id: e.position for e in SNAPSHOT.entities if e.kind == "npc"}


def village() -> tuple[Movement, Errands, list[EntityMoved]]:
    bus = EventBus()
    moved: list[EntityMoved] = []
    bus.subscribe(EntityMoved, moved.append)
    movement = Movement(TOWN, bus)
    return movement, Errands(movement, SNAPSHOT.entities), moved


def run(movement: Movement, errands: Errands, seconds: float) -> None:
    for _ in range(round(seconds / STEP)):
        errands.tick(STEP)
        movement.tick(STEP)


def tiles(moved: list[EntityMoved], entity: str) -> list[tuple[float, float]]:
    return [(e.x, e.y) for e in moved if e.entity == entity]


def test_places_every_npc_on_its_doorstep() -> None:
    movement, _, moved = village()

    assert {e.entity: Position(x=e.x, y=e.y) for e in moved} == NPCS
    assert {id: Position(x=p.x, y=p.y) for id, p in movement.entities().items()} == NPCS


def test_npcs_set_off_one_after_another() -> None:
    movement, errands, moved = village()

    run(movement, errands, 3)
    assert {e.entity for e in moved[len(NPCS) :]} == {"mei"}

    run(movement, errands, 6)
    assert {e.entity for e in moved[len(NPCS) :]} == set(NPCS)


def test_npcs_walk_neighbouring_tiles() -> None:
    movement, errands, moved = village()

    run(movement, errands, 60)

    for npc in NPCS:
        path = tiles(moved, npc)
        assert len(path) > 10
        for (x0, y0), (x1, y1) in zip(path, path[1:], strict=False):
            assert max(abs(x1 - x0), abs(y1 - y0)) == 1
            assert TOWN.walkable(int(x1), int(y1))


def test_mei_runs_her_errands_and_comes_home_again() -> None:
    movement, errands, moved = village()
    home = (NPCS["mei"].x, NPCS["mei"].y)

    run(movement, errands, 150)

    path = tiles(moved, "mei")
    visited = [
        location.id
        for tile in path
        for location in TOWN.locations
        if location.entry.x == tile[0] and location.entry.y == tile[1]
    ]
    assert visited[:4] == ["house_1", "coffee_shop", "square", "house_1"]
    assert path.count(home) >= 2


def test_snapshot_shows_where_everyone_is_now() -> None:
    movement, errands, _ = village()
    run(movement, errands, 20)

    snapshot = errands.snapshot(SNAPSHOT)

    for entity in snapshot.entities:
        if entity.id in NPCS:
            point = movement.position(entity.id)
            assert entity.position == Position(x=point.x, y=point.y)
        else:
            assert entity in SNAPSHOT.entities
    assert snapshot.entities != SNAPSHOT.entities
