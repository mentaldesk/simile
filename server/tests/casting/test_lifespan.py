from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from starlette.applications import Starlette

from simile.app import create_app
from simile.behaviour import behaviour_of
from simile.casting import Cast, bind, cast, write_cast
from simile.memory import MemoryStore, memory_of
from simile.persistence import WorldStore
from simile.schema import Character, Memory, MemoryKind
from simile.sim import Clock, FakeWallClock, World, world_of

START = datetime(2026, 10, 18, 8, tzinfo=UTC)
HOUSES = [f"house_{n}" for n in range(1, 11)]


async def start_village(minutes: float = 0) -> Starlette:
    app = create_app()
    app.state.world = World(Clock(START), FakeWallClock())
    app.state.headless = True
    async with app.router.lifespan_context(app):
        await world_of(app).loop.run(timedelta(minutes=minutes))
    return app


def past(database: Path, ids: list[str]) -> list[Memory]:
    with MemoryStore(database) as store:
        return [m for id in ids for m in store.recall(id, START, kind=MemoryKind.PAST, k=1000)]


@pytest.fixture
def made(pool: list[Character], world: Path) -> Cast:
    made = bind(cast(pool, 5, seed=3, houses=10), seed=3, houses=HOUSES)
    write_cast(made, world)
    return made


@pytest.mark.anyio
async def test_the_server_runs_the_cast_with_its_history(world: Path, made: Cast) -> None:
    ids = [r.character.id for r in made.residents]

    app = await start_village(minutes=1)

    assert sorted(behaviour_of(app).npcs) == sorted(ids)
    with MemoryStore(world / "simile.db") as store:
        bonded = {(r.owner, r.about) for id in ids for r in store.relationships(id)}
    assert bonded == {
        pair
        for bond in made.bonds
        for pair in ((bond.actor, bond.target), (bond.target, bond.actor))
    }
    expected = sum(len(r.character.past) for r in made.residents) + 2 * len(made.bonds)
    assert len(past(world / "simile.db", ids)) == expected


@pytest.mark.anyio
async def test_the_history_is_seeded_once_and_again_after_a_reset(world: Path, made: Cast) -> None:
    ids = [r.character.id for r in made.residents]
    await start_village()
    seeded = past(world / "simile.db", ids)

    await start_village()
    assert past(world / "simile.db", ids) == seeded

    with MemoryStore(world / "simile.db") as memory, WorldStore(memory) as store:
        store.clear()
    app = await start_village()
    assert len(past(world / "simile.db", ids)) == len(seeded)
    assert memory_of(app).path == world / "simile.db"


@pytest.mark.anyio
async def test_todays_village_gets_no_cast_history(world: Path) -> None:
    app = await start_village()

    assert "kofi" in behaviour_of(app).npcs
    assert past(world / "simile.db", list(behaviour_of(app).npcs)) == []
