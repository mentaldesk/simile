from collections.abc import Callable
from datetime import UTC, datetime

from starlette.testclient import TestClient

from simile.app import create_app
from simile.behaviour import Activity, Goal
from simile.cafe.events import Served
from simile.economy import Kind
from simile.sim import Clock, World, world_of

MakePackage = Callable[[dict[str, str]], str]


def test_the_server_keeps_everyones_money_and_plugs_it_into_behaviour(
    make_package: MakePackage,
) -> None:
    lifespans = ("behaviour", "economy", "memory", "protocol", "world")
    files = {f"{m}/lifespan.py": f"from simile.{m}.lifespan import lifespan\n" for m in lifespans}
    app = create_app(make_package(files))
    app.state.world = World(Clock(datetime(2026, 1, 1, 10, tzinfo=UTC)))

    with TestClient(app) as client:
        economy, behaviour = app.state.economy, app.state.behaviour
        kofi = behaviour.npcs["kofi"]
        assert behaviour.hooks.money(kofi) == kofi.money
        assert behaviour.hooks.earnings(kofi, Goal(Activity.WORK, kofi.workplace)) > 0

        world_of(app).bus.publish(Served("kofi", "mirela", "flat white", 30.0, False))
        client.portal.call(world_of(app).loop.tick)

        assert [e.kind for e in economy.ledger.entries] == [Kind.PURCHASE, Kind.SUPPLIES]
        assert economy.money["kofi"] < kofi.money
    assert behaviour.hooks.money(kofi) is None
