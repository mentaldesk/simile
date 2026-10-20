import pytest

from simile.behaviour import DEFAULT_CONFIG, Activity, Goal, Need
from simile.cafe.cafe import Phase, Step
from simile.cafe.events import Ordered, Served
from simile.schema import MapTile, Npc, Pay, PayKind, Shift, Weekday
from simile.world import Point

from .conftest import ANA, BEA, DAY, GROUND, Village, keen

pytestmark = pytest.mark.anyio

TILL = Point(3, 2, GROUND)
CAFE = Goal(Activity.COFFEE_SHOP, "coffee_shop")
COFFEE = keen(Activity.COFFEE_SHOP)


def barista(**values: float) -> Npc:
    """Dee, who works the café's 07:00 to 17:00 every day for its takings and lives elsewhere."""
    return BEA.model_copy(
        update={
            "id": "dee",
            "name": "Dee Test",
            "home": "house_4",
            "workplace": "coffee_shop",
            "shifts": [Shift(days=list(Weekday), start=7, end=17)],
            "pay": Pay(kind=PayKind.TAKINGS),
            "money": 1000.0,
            "values": {**BEA.values, **values},
        }
    )


async def test_the_cafe_opens_when_its_barista_gets_to_work_however_late() -> None:
    late = DEFAULT_CONFIG.model_copy(update={"set_off_jitter": 0.0, "skip": 0.0})
    dawn = DAY.replace(hour=6, minute=30)
    village = Village((barista(discipline=0.0),), start=dawn, behaviour=late)

    await village.run(minutes=37)
    assert village.cafe.open and not village.cafe.on_shift

    await village.run_until(lambda: village.cafe.on_shift, minutes=60)
    assert village.now > DAY.replace(hour=7, minute=10)
    await village.run_until(lambda: village.at("dee") == TILL, minutes=5)
    assert village.cafe.serving
    assert village.behaviour.working("dee")


async def test_a_skipped_shift_keeps_the_cafe_shut_and_its_customers_sit_down() -> None:
    skipping = COFFEE.model_copy(update={"skip": 1.0})
    village = Village((barista(responsibility=0.0), ANA), behaviour=skipping)

    await village.run(minutes=15)

    assert village.behaviour.goal("ana") == CAFE and village.at("ana").map in village.cafe.maps
    assert not village.cafe.on_shift
    assert village.cafe.queue == [] and village.of(Ordered) == []
    assert village.cafe.supply(CAFE, Need.HUNGER) == 0.0


async def test_the_barista_stays_until_the_end_of_their_shift_then_goes() -> None:
    village = Village((barista(),), start=DAY.replace(hour=16, minute=50))
    await village.run_until(lambda: village.cafe.on_shift, minutes=5)

    await village.run_until(lambda: not village.cafe.on_shift, minutes=15)

    assert village.now >= DAY.replace(hour=17)
    assert village.behaviour.minds["dee"].held is None


async def test_the_queue_is_let_go_if_the_barista_is_called_away() -> None:
    working = COFFEE.model_copy(update={"base": {Activity.COFFEE_SHOP: 10.0, Activity.WORK: 20.0}})
    village = Village((barista(), ANA), start=DAY.replace(hour=10), behaviour=working)
    await village.run_until(lambda: "ana" in village.cafe.queue and village.cafe.on_shift)

    village.behaviour.release("dee")
    village.cafe.tick(0.1)

    cafe = village.cafe
    assert not cafe.on_shift and cafe.job is None
    assert "ana" not in cafe.visits and "ana" not in cafe.queue
    assert village.behaviour.minds["ana"].held is None
    assert "ana" not in village.behaviour.leave_player_alone
    await village.run_until(lambda: cafe.on_shift, minutes=5)


async def test_a_customer_let_go_mid_order_takes_their_order_with_them() -> None:
    village = Village((BEA, ANA), behaviour=COFFEE)
    cafe = village.cafe
    await village.run_until(lambda: cafe.job is not None and cafe.job.step is Step.MAKING)
    assert cafe.visits["ana"].phase is Phase.WAITING

    village.behaviour.release("ana")
    village.cafe.tick(0.1)

    assert cafe.job is None and "ana" not in cafe.visits
    held = village.behaviour.minds["bea"].held
    assert held is not None and held[0] == MapTile(map=GROUND, x=3, y=2)
    assert village.of(Served) == []
