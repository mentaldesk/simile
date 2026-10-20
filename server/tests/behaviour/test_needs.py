from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.app import create_app
from simile.behaviour import DEFAULT_CONFIG, Activity, Behaviour, Goal, Need
from simile.behaviour.scoring import worth
from simile.cafe.cafe import Cafe
from simile.memory import MemoryStore
from simile.npc import load_npcs
from simile.schema import CoreValue, MapTile, Npc
from simile.sim import STEP, Clock, FakeWallClock, World, world_of
from simile.world import Movement
from simile.world.map import load_maps

MAPS = load_maps()
TEMPLATE = load_npcs()[0]
DAY = datetime(2026, 1, 1, tzinfo=UTC)
A = Activity
PARK = Goal(A.PARK, "park")
CAFE = Goal(A.COFFEE_SHOP, "coffee_shop")
NOODLES = Goal(A.NOODLE_BAR, "noodle_bar")
KITCHENS = {A.HOME, A.COFFEE_SHOP, A.NOODLE_BAR}
STEADY = DEFAULT_CONFIG.model_copy(update={"temperature": 0.0})

MakePackage = Callable[[dict[str, str]], str]


NO_WORK = {"workplace": None, "shifts": [], "pay": None}


def make_npc(id: str, home: str, **values: float) -> Npc:
    scores = {value: values.get(value.value, 0.5) for value in CoreValue}
    return TEMPLATE.model_copy(
        update={
            "id": id,
            "name": f"{id.title()} Test",
            "home": home,
            "values": scores,
            "craft": None,
            **NO_WORK,
        }
    )


ANA = make_npc("ana", "house_1")
BEA = make_npc("bea", "coffee_shop")


class Village:
    def __init__(
        self, npcs: list[Npc], *, hour: float = 11, placed: dict[str, str] | None = None
    ) -> None:
        self.world = World(Clock(DAY + timedelta(hours=hour)), FakeWallClock())
        self.movement = Movement(MAPS, self.world.bus)
        self.store = MemoryStore(":memory:")
        self.behaviour = Behaviour(
            self.world.clock, self.world.bus, self.movement, npcs, self.store, config=STEADY, seed=0
        )
        self.world.loop.register(self.behaviour)
        self.world.loop.register(self.movement)
        for npc, place in (placed or {}).items():
            self.movement.place(npc, place)
        self.behaviour.start()

    @property
    def now(self) -> datetime:
        return self.world.clock.now

    def run(self, *, minutes: float) -> None:
        for _ in range(round(minutes * 60 / STEP)):
            self.world.loop.tick()

    def run_until(self, done: Callable[[], bool], *, minutes: float = 30) -> None:
        end = self.now + timedelta(minutes=minutes)
        while not done():
            assert self.now < end, "ran out of time"
            self.world.loop.tick()

    def stay(self, npc: str, goal: Goal, minutes: float = 60, **needs: float) -> None:
        """Put them partway through a stay at `goal`, with the needs given."""
        mind = self.behaviour.minds[npc]
        levels = {**mind.needs, **{Need(need): level for need, level in needs.items()}}
        until = self.now + timedelta(minutes=minutes)
        self.behaviour.restore(npc, goal, levels, self.now, until, {})

    def set(self, npc: str, **needs: float) -> None:
        for need, level in needs.items():
            self.behaviour.minds[npc].needs[Need(need)] = level


def test_urgent_hunger_ends_a_stay_early_for_a_meal() -> None:
    village = Village([ANA], placed={"ana": "park"})
    village.stay("ana", PARK, hunger=0.5)
    village.run(minutes=5)
    assert village.behaviour.goal("ana") == PARK

    village.set("ana", hunger=0.95)
    village.run(minutes=0.1)

    mind = village.behaviour.minds["ana"]
    assert mind.goal.activity in KITCHENS
    assert mind.walk is not None


def test_a_stay_that_meets_the_urgent_need_carries_on() -> None:
    village = Village([ANA], placed={"ana": "house_1"})
    home = Goal(A.HOME, "house_1")
    village.stay("ana", home, hunger=0.95)

    village.run(minutes=5)

    assert village.behaviour.goal("ana") == home
    assert village.behaviour.needs("ana")[Need.HUNGER] < 0.9


def test_wants_never_interrupt_only_bodily_needs_do() -> None:
    village = Village([ANA], placed={"ana": "park"})
    village.stay("ana", PARK, social=1.0, news=1.0, rest=1.0, curiosity=1.0, exercise=1.0)

    village.run(minutes=5)

    assert village.behaviour.goal("ana") == PARK


def test_a_held_resident_stays_put_while_their_spot_meets_the_need() -> None:
    village = Village([ANA])
    spot = MapTile(map="coffee_shop_floor_0", x=3, y=2)
    village.behaviour.hold("ana", spot, CAFE)
    village.run(minutes=10)

    village.set("ana", hunger=0.95)
    village.run(minutes=1)
    assert village.behaviour.minds["ana"].held is not None

    village.behaviour.hooks.set(supply=shut_cafe)
    village.set("ana", hunger=0.0)
    village.run(minutes=0.1)
    village.set("ana", hunger=0.95)
    village.run(minutes=0.1)
    mind = village.behaviour.minds["ana"]
    assert mind.held is None
    assert mind.goal != CAFE and mind.goal.activity in KITCHENS


def shut_cafe(goal: Goal, need: Need) -> float:
    return 0.0 if goal == CAFE else 1.0


def test_a_second_meal_straight_after_the_first_is_worth_far_less() -> None:
    meal = -0.6

    first = worth(Need.HUNGER, 0.9, meal)
    second = worth(Need.HUNGER, 0.9 + meal, meal)

    assert first == pytest.approx(16 * (0.9**4 - 0.3**4) / 4)
    assert second < first / 50


def test_eating_happens_once_they_are_hungry_and_stops_when_they_are_full() -> None:
    village = Village([ANA], placed={"ana": "noodle_bar"})
    village.stay("ana", NOODLES, hunger=0.5)
    village.run(minutes=10)
    peckish = village.behaviour.needs("ana")[Need.HUNGER]
    assert peckish > 0.5

    village.stay("ana", NOODLES, hunger=0.85)
    village.run(minutes=25)
    full = village.behaviour.needs("ana")[Need.HUNGER]
    assert full < 0.05

    village.run(minutes=15)
    assert full < village.behaviour.needs("ana")[Need.HUNGER] < 0.1


def test_a_shut_place_feeds_nobody() -> None:
    village = Village([ANA], placed={"ana": "coffee_shop"})
    village.behaviour.hooks.set(supply=lambda goal, need: 0.0 if need is Need.HUNGER else 1.0)
    village.stay("ana", CAFE, hunger=0.85, relaxation=0.6)

    village.run(minutes=10)

    needs = village.behaviour.needs("ana")
    assert needs[Need.HUNGER] > 0.85
    assert needs[Need.RELAXATION] < 0.6


def test_a_meal_under_way_is_finished_when_the_place_stops_serving() -> None:
    village = Village([ANA], placed={"ana": "noodle_bar"})
    village.stay("ana", NOODLES, hunger=0.85)
    village.run(minutes=2)
    assert village.behaviour.needs("ana")[Need.HUNGER] < 0.85

    village.behaviour.hooks.set(supply=lambda goal, need: 0.0 if need is Need.HUNGER else 1.0)
    village.run(minutes=10)

    assert village.behaviour.needs("ana")[Need.HUNGER] < 0.4


def test_they_wake_hungry_but_not_lonely() -> None:
    village = Village([ANA], hour=3)
    before = village.behaviour.needs("ana")

    village.run(minutes=60)

    after = village.behaviour.needs("ana")
    config = DEFAULT_CONFIG
    awake = config.rise[Need.HUNGER] + config.rise_values[Need.HUNGER][CoreValue.PLEASURE] * 0.5
    assert village.behaviour.goal("ana").activity is A.SLEEP
    assert after[Need.HUNGER] - before[Need.HUNGER] == pytest.approx(
        awake * config.rise_asleep[Need.HUNGER], rel=0.02
    )
    assert after[Need.SOCIAL] == before[Need.SOCIAL]


class CafeVillage:
    """The café on the loop with its barista and one customer, as G1 runs it."""

    def __init__(self, hour: float) -> None:
        self.village = Village([BEA, ANA], hour=hour)
        village = self.village
        self.cafe = Cafe(
            village.world.clock,
            village.world.bus,
            village.behaviour,
            village.store,
            lambda: None,
            seed=0,
        )
        village.world.loop.register(self.cafe)
        village.behaviour.hooks.set(supply=self.cafe.supply)

    def queuing(self) -> None:
        """Send the customer in, and wait until she's queuing."""
        village = self.village
        village.behaviour.nudge("ana", CAFE, 50.0)
        village.run_until(lambda: "ana" in self.cafe.queue)


def test_a_resident_queuing_at_the_cafe_is_not_pulled_away_by_a_need_it_meets() -> None:
    town = CafeVillage(hour=10)
    village, behaviour = town.village, town.village.behaviour
    town.queuing()

    village.set("ana", hunger=0.95, exercise=1.0)
    village.run(minutes=0.5)

    assert behaviour.minds["ana"].held is not None
    assert behaviour.goal("ana") == CAFE


def test_the_cafe_lets_go_cleanly_of_someone_an_urgent_need_takes_away() -> None:
    town = CafeVillage(hour=10)
    village, behaviour = town.village, town.village.behaviour
    town.queuing()

    behaviour.hooks.set(supply=shut_cafe)
    village.set("ana", hunger=0.95)
    village.run(minutes=0.5)

    assert behaviour.minds["ana"].held is None
    assert behaviour.goal("ana") != CAFE
    assert "ana" not in town.cafe.visits and "ana" not in town.cafe.queue
    assert "ana" not in behaviour.leave_player_alone
    assert town.cafe.on_shift and behaviour.minds["bea"].held is not None


@pytest.mark.parametrize(("hour", "fed"), [(6, 0.0), (10, 1.0), (18, 0.0)])
def test_the_daily_grind_feeds_people_only_while_the_barista_is_on_shift(
    hour: float, fed: float
) -> None:
    town = CafeVillage(hour=hour)
    town.village.run(minutes=0.1)

    assert town.cafe.supply(CAFE, Need.HUNGER) == fed
    assert town.cafe.supply(CAFE, Need.RELAXATION) == 1.0
    assert town.cafe.supply(Goal(A.HOME, "coffee_shop"), Need.HUNGER) == 1.0


def make_app(make_package: MakePackage, hour: float) -> Starlette:
    lifespans = ("behaviour", "conversation", "llm", "memory", "protocol", "world")
    files = {f"{m}/lifespan.py": f"from simile.{m}.lifespan import lifespan\n" for m in lifespans}
    files["cafe/lifespan.py"] = "from simile.cafe.lifespan import running\n"
    app = create_app(make_package(files))
    app.state.world = World(Clock(DAY + timedelta(hours=hour)))
    return app


def test_the_server_plugs_the_cafes_shift_into_behaviour(make_package: MakePackage) -> None:
    app = make_app(make_package, hour=10)

    with TestClient(app) as client:
        behaviour = app.state.behaviour
        client.portal.call(world_of(app).loop.tick)
        assert behaviour.hooks.supply(CAFE, Need.HUNGER) == 0.0
        send_to_work(behaviour, app.state.cafe.barista)
        client.portal.call(world_of(app).loop.tick)
        assert app.state.cafe.on_shift
        assert behaviour.hooks.supply(CAFE, Need.HUNGER) == 1.0

    assert behaviour.hooks.supply(CAFE, Need.HUNGER) == 1.0


def send_to_work(behaviour: Behaviour, npc: str) -> None:
    """Send them to work now, as their shift would, rather than wait on unseeded B1."""
    now, needs = behaviour.clock.now, behaviour.needs(npc)
    behaviour.restore(npc, Goal(A.WORK, "coffee_shop"), needs, now, now + timedelta(hours=1), {})
