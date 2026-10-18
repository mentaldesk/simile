from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.app import create_app
from simile.behaviour import Activity, Goal, Need
from simile.sim import Clock, World, world_of

MakePackage = Callable[[dict[str, str]], str]

START = datetime(2026, 1, 1, 10, tzinfo=UTC)
LIFESPANS = ("behaviour", "conversation", "economy", "llm", "memory", "protocol", "world")
CAFE = Goal(Activity.COFFEE_SHOP, "coffee_shop")
NOODLES = Goal(Activity.NOODLE_BAR, "noodle_bar")


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
        send_to_work(app)
        client.portal.call(world_of(app).loop.tick)
        assert cafe.on_shift
        assert app.state.behaviour.goal(cafe.barista) == CAFE

    assert cafe.barista not in players.writers


def test_the_cafes_supply_hook_wraps_the_economys(make_package: MakePackage) -> None:
    app = make_app(make_package)

    with TestClient(app) as client:
        behaviour, economy = app.state.behaviour, app.state.economy
        assert behaviour.hooks.supply(CAFE, Need.HUNGER) == 0.0
        send_to_work(app)
        assert economy.staffed("coffee_shop") and not app.state.cafe.on_shift
        assert behaviour.hooks.supply(CAFE, Need.HUNGER) == 0.0
        client.portal.call(world_of(app).loop.tick)
        until(client, app, lambda: economy.staffed("coffee_shop"))
        assert behaviour.hooks.supply(CAFE, Need.HUNGER) == 1.0
        economy.fridges["house_3"] = 0
        assert behaviour.hooks.supply(Goal(Activity.HOME, "house_3"), Need.HUNGER) == 0.0
        assert behaviour.hooks.supply(NOODLES, Need.HUNGER) == 0.0

    assert behaviour.hooks.supply(CAFE, Need.HUNGER) == 1.0


def send_to_work(app: Starlette) -> None:
    """Send the barista to work now, as their shift would, rather than wait on unseeded B1."""
    behaviour, barista = app.state.behaviour, app.state.cafe.barista
    now, needs = behaviour.clock.now, behaviour.needs(barista)
    work = Goal(Activity.WORK, "coffee_shop")
    behaviour.restore(barista, work, needs, now, now + timedelta(hours=1), {})


def until(client: TestClient, app: Starlette, done: Callable[[], bool], ticks: int = 3000) -> None:
    for _ in range(ticks):
        if done():
            return
        client.portal.call(world_of(app).loop.tick)
    raise AssertionError("ran out of time")
