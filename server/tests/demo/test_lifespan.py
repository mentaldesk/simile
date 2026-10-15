from collections.abc import Callable
from dataclasses import dataclass, field

import pytest
from starlette.testclient import TestClient

from simile.app import create_app
from simile.protocol import Entity, hub_of
from simile.protocol.fixtures import fixture_world
from simile.sim import EntityMoved, world_of

MakePackage = Callable[[dict[str, str]], str]

LIFESPANS = {
    "demo/lifespan.py": "from simile.demo.lifespan import lifespan\n",
    "world/lifespan.py": "from simile.world.lifespan import lifespan\n",
}
FIXTURES: list[Entity] = fixture_world()[0]
NPCS = {e.id for e in FIXTURES if e.kind == "npc"}


@dataclass
class Run:
    moved: set[str] = field(default_factory=set)
    snapshot_moved: set[str] = field(default_factory=set)
    moved_after: set[str] = field(default_factory=set)
    snapshot_after: list[Entity] = field(default_factory=list)


def run(make_package: MakePackage, headless: bool = False, seconds: int = 10) -> Run:
    app = create_app(make_package(LIFESPANS))
    app.state.headless = headless
    world, hub = world_of(app), hub_of(app)
    result = Run()
    moving = result.moved
    world.bus.subscribe(EntityMoved, lambda event: moving.add(event.entity))

    with TestClient(app):
        for _ in range(seconds * 10):
            world.loop.tick()
        result.snapshot_moved = {e.id for e in hub.snapshot().entities if e not in FIXTURES}
    moving = result.moved_after
    for _ in range(seconds * 10):
        world.loop.tick()
    result.snapshot_after = hub.snapshot().entities
    return result


def test_is_off_by_default(make_package: MakePackage, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SIMILE_DEMO", raising=False)
    assert run(make_package) == Run(snapshot_after=FIXTURES)


def test_walks_the_fixture_npcs_when_turned_on(
    make_package: MakePackage, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SIMILE_DEMO", "1")
    result = run(make_package)
    assert result.moved == result.snapshot_moved == NPCS


def test_stops_and_restores_the_snapshot_on_shutdown(
    make_package: MakePackage, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SIMILE_DEMO", "1")
    result = run(make_package)
    assert result.moved_after == set()
    assert result.snapshot_after == FIXTURES


def test_stays_off_when_headless(
    make_package: MakePackage, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SIMILE_DEMO", "1")
    assert run(make_package, headless=True) == Run(snapshot_after=FIXTURES)
