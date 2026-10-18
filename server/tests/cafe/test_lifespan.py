from collections.abc import Callable
from datetime import UTC, datetime

from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.app import create_app
from simile.behaviour import Activity, Goal
from simile.sim import Clock, World, world_of

MakePackage = Callable[[dict[str, str]], str]

START = datetime(2026, 1, 1, 10, tzinfo=UTC)
LIFESPANS = ("behaviour", "conversation", "llm", "memory", "protocol", "world")


def make_app(make_package: MakePackage) -> Starlette:
    files = {f"{m}/lifespan.py": f"from simile.{m}.lifespan import lifespan\n" for m in LIFESPANS}
    files["cafe/lifespan.py"] = "from simile.cafe.lifespan import running\n"
    app = create_app(make_package(files))
    app.state.world = World(Clock(START))
    return app


def test_the_cafe_runs_on_the_loop_and_takes_the_players_orders(make_package: MakePackage) -> None:
    app = make_app(make_package)

    with TestClient(app) as client:
        cafe, players = app.state.cafe, app.state.players
        assert cafe.barista is not None
        assert players.writers[cafe.barista] == cafe.write
        client.portal.call(world_of(app).loop.tick)
        assert cafe.on_shift
        assert app.state.behaviour.goal(cafe.barista) == Goal(Activity.COFFEE_SHOP, "coffee_shop")

    assert cafe.barista not in players.writers
