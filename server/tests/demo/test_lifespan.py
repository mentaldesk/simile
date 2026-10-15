import asyncio
from dataclasses import dataclass, field

import pytest
from starlette.applications import Starlette

from simile.demo.lifespan import lifespan
from simile.protocol import hub_of
from simile.sim import EntityMoved, world_of

NPCS = {"mei", "viktor", "suki"}


@dataclass
class Run:
    moved: set[str] = field(default_factory=set)
    moved_after: set[str] = field(default_factory=set)
    snapshot_moved: set[str] = field(default_factory=set)
    snapshot_restored: bool = False


def run(app: Starlette, seconds: int = 10) -> Run:
    world, hub = world_of(app), hub_of(app)
    fixtures = hub.snapshot().entities
    result = Run()
    moving = result.moved
    world.bus.subscribe(EntityMoved, lambda event: moving.add(event.entity))

    async def go() -> None:
        nonlocal moving
        async with lifespan(app):
            for _ in range(seconds * 10):
                world.loop.tick()
            result.snapshot_moved = {e.id for e in hub.snapshot().entities if e not in fixtures}
        moving = result.moved_after
        for _ in range(seconds * 10):
            world.loop.tick()
        result.snapshot_restored = hub.snapshot().entities == fixtures

    asyncio.run(go())
    return result


def test_is_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SIMILE_DEMO", raising=False)
    assert run(Starlette()) == Run(snapshot_restored=True)


def test_walks_the_fixture_npcs_when_turned_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIMILE_DEMO", "1")
    result = run(Starlette())
    assert result.moved == result.snapshot_moved == NPCS


def test_stops_and_restores_the_snapshot_on_shutdown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIMILE_DEMO", "1")
    result = run(Starlette())
    assert result.moved_after == set()
    assert result.snapshot_restored


def test_stays_off_when_headless(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIMILE_DEMO", "1")
    app = Starlette()
    app.state.headless = True
    assert run(app) == Run(snapshot_restored=True)
