from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from simile.behaviour import DEFAULT_CONFIG, Activity, Behaviour, BehaviourConfig, Goal, Need
from simile.cafe.events import Served
from simile.economy import DEFAULT_CONFIG as ECONOMY
from simile.economy import OUTSIDE, Kind
from simile.economy.economy import Economy, Turn
from simile.memory import MemoryStore
from simile.npc import load_npcs
from simile.schema import CoreValue, Npc, Pay, PayKind, Shift, Weekday
from simile.sim import STEP, Clock, FakeWallClock, World
from simile.world import Movement
from simile.world.map import load_maps

MAPS = load_maps()
TEMPLATE = load_npcs()[0]
THURSDAY = datetime(2026, 1, 1, tzinfo=UTC)
STEADY = DEFAULT_CONFIG.model_copy(update={"temperature": 0.0, "set_off_jitter": 0.0})
A = Activity
NOODLES = Goal(A.NOODLE_BAR, "noodle_bar")
CAFE = Goal(A.COFFEE_SHOP, "coffee_shop")


def resident(
    id: str,
    home: str = "house_1",
    *,
    workplace: str | None = None,
    hours: tuple[float, float] = (9, 13),
    pay: Pay | None = None,
    money: float = 200.0,
    **values: float,
) -> Npc:
    scores = {value: values.get(value.value, 0.5) for value in CoreValue}
    shifts = [Shift(days=list(Weekday), start=hours[0], end=hours[1])] if workplace else []
    return TEMPLATE.model_copy(
        update={
            "id": id,
            "name": f"{id.title()} Test",
            "home": home,
            "workplace": workplace,
            "shifts": shifts,
            "pay": pay,
            "money": money,
            "values": scores,
            "craft": None,
        }
    )


def wage(amount: float) -> Pay:
    return Pay(kind=PayKind.WAGE, amount=amount)


TAKINGS = Pay(kind=PayKind.TAKINGS)


class Town:
    def __init__(
        self, npcs: list[Npc], *, hour: float = 8, config: BehaviourConfig = STEADY
    ) -> None:
        self.world = World(Clock(THURSDAY + timedelta(hours=hour)), FakeWallClock())
        self.movement = Movement(MAPS, self.world.bus)
        self.behaviour = Behaviour(
            self.world.clock,
            self.world.bus,
            self.movement,
            npcs,
            MemoryStore(":memory:"),
            config=config,
            seed=0,
        )
        self.economy = Economy(self.world.clock, self.behaviour)
        self.behaviour.hooks.set(
            money=self.economy.money_of,
            price=self.economy.price,
            earnings=self.economy.earnings,
            supply=self.economy.supply,
        )
        self.world.bus.subscribe(Served, self.economy.on_served)
        for system in (self.behaviour, self.movement, self.economy):
            self.world.loop.register(system)
        self.behaviour.start()

    @property
    def now(self) -> datetime:
        return self.world.clock.now

    def run(self, *, minutes: float) -> None:
        for _ in range(round(minutes * 60 / STEP)):
            self.world.loop.tick()

    def until(self, done: Callable[[], bool], *, hours: float = 12) -> None:
        end = self.now + timedelta(hours=hours)
        while not done():
            assert self.now < end, "ran out of time"
            self.world.loop.tick()

    def stay(self, npc: str, goal: Goal, minutes: float = 60, **needs: float) -> None:
        mind = self.behaviour.minds[npc]
        levels = {**mind.needs, **{Need(need): level for need, level in needs.items()}}
        self.behaviour.restore(
            npc, goal, levels, self.now, self.now + timedelta(minutes=minutes), {}
        )

    def kinds(self, npc: str) -> list[Kind]:
        return [e.kind for e in self.economy.ledger.entries if npc in (e.payer, e.payee)]


def test_a_wage_is_paid_for_the_hours_worked() -> None:
    town = Town([resident("ana", workplace="park", pay=wage(20))], hour=9)
    town.movement.place("ana", "park")
    town.stay("ana", Goal(A.WORK, "park"), minutes=150)

    town.run(minutes=150.2)

    wages = [e for e in town.economy.ledger.entries if e.kind is Kind.WAGE]
    assert [e.payer for e in wages] == [OUTSIDE] * len(wages)
    assert len(wages) >= 3
    assert sum(e.amount for e in wages) == pytest.approx(20 * 2.5, abs=0.1)
    assert town.economy.money["ana"] == pytest.approx(200 + 50, abs=0.1)


def test_rent_and_a_days_pension_come_at_midnight() -> None:
    town = Town(
        [
            resident("ana", pay=Pay(kind=PayKind.PENSION, amount=280)),
            resident("bea", "house_2"),
        ],
        hour=23.5,
    )

    town.run(minutes=29.9)
    assert town.economy.ledger.entries == []

    town.run(minutes=0.2)

    assert town.economy.money == pytest.approx({"ana": 200 - 30 + 40, "bea": 200 - 30})
    assert sorted(town.kinds("ana")) == [Kind.PENSION, Kind.RENT]
    town.run(minutes=60)
    assert len(town.economy.ledger.entries) == 3


def test_paying_at_a_shop_pays_whoever_runs_it_less_their_supplies() -> None:
    cook = resident("cook", "house_2", workplace="noodle_bar", hours=(11, 21), pay=TAKINGS)
    town = Town([resident("ana"), cook], hour=12)
    town.movement.place("cook", "noodle_bar")
    town.stay("cook", Goal(A.WORK, "noodle_bar"), minutes=600)
    town.run(minutes=0.2)
    town.movement.place("ana", "noodle_bar")
    town.stay("ana", NOODLES, hunger=0.85)

    town.run(minutes=10)

    shop = town.economy.config.shops["noodle_bar"]
    paid = {(e.kind, e.payer, e.payee, round(e.amount, 6)) for e in town.economy.ledger.entries}
    assert paid == {
        (Kind.PURCHASE, "ana", "cook", shop.drink),
        (Kind.SUPPLIES, "cook", OUTSIDE, round(shop.drink * shop.supplies, 6)),
        (Kind.PURCHASE, "ana", "cook", shop.meal),
        (Kind.SUPPLIES, "cook", OUTSIDE, round(shop.meal * shop.supplies, 6)),
    }
    spent = shop.drink + shop.meal
    assert town.economy.money == pytest.approx(
        {"ana": 200 - spent, "cook": 200 + spent * (1 - shop.supplies)}
    )


def test_a_shop_nobody_runs_feeds_nobody() -> None:
    town = Town([resident("ana")], hour=12)
    town.movement.place("ana", "noodle_bar")
    town.stay("ana", NOODLES, hunger=0.85)

    town.run(minutes=10)

    assert town.economy.ledger.entries == []
    assert town.behaviour.needs("ana")[Need.HUNGER] > 0.85


def test_a_drink_at_a_cafe_nobody_runs_for_takings_is_paid_outside_the_village() -> None:
    town = Town([resident("ana"), resident("mia", "coffee_shop")])

    town.world.bus.publish(Served("ana", "mia", "flat white", 30.0, False))

    [drink] = town.economy.ledger.entries
    assert (drink.kind, drink.payer, drink.payee) == (Kind.PURCHASE, "ana", OUTSIDE)


def test_a_drink_the_cafe_serves_is_paid_for() -> None:
    barista = resident("mia", "coffee_shop", workplace="coffee_shop", hours=(7, 17), pay=TAKINGS)
    town = Town([resident("ana"), barista])

    town.world.bus.publish(Served("ana", "mia", "flat white", 30.0, False))
    town.world.bus.publish(Served("player", "mia", "espresso", 30.0, False))

    drink = town.economy.config.shops["coffee_shop"].drink
    assert town.economy.money["ana"] == 200 - drink
    assert [e.kind for e in town.economy.ledger.entries] == [Kind.PURCHASE, Kind.SUPPLIES]


def test_the_ledger_balances_after_a_day() -> None:
    npcs = [
        resident("ana", workplace="park", hours=(9, 13), pay=wage(20)),
        resident("bea", "house_2", workplace="noodle_bar", hours=(11, 21), pay=TAKINGS),
        resident("cy", "house_3", pay=Pay(kind=PayKind.PENSION, amount=300)),
        resident("dee", "coffee_shop", workplace="coffee_shop", hours=(7, 17), pay=TAKINGS),
    ]
    town = Town(npcs, hour=6)

    town.run(minutes=26 * 60)

    book = town.economy.ledger
    kinds = book.by_kind()
    assert {Kind.WAGE, Kind.PENSION, Kind.RENT, Kind.GROCERIES} <= set(kinds)
    assert book.gap(town.economy.money) == pytest.approx(0, abs=1e-6)
    assert book.held() == pytest.approx(town.economy.money)


def test_prices_follow_what_they_would_buy() -> None:
    mia = resident("mia", "coffee_shop", workplace="coffee_shop", hours=(7, 17), pay=TAKINGS)
    town = Town([resident("ana"), mia], hour=12)
    town.movement.place("mia", "coffee_shop")
    town.stay("mia", Goal(A.WORK, "coffee_shop"), minutes=600)
    town.run(minutes=0.2)
    town.behaviour.hooks.set(supply=lambda goal, need: 1.0)
    economy, ana = town.economy, town.behaviour.npcs["ana"]
    shops = economy.config.shops
    home = Goal(A.HOME, "house_1")

    town.behaviour.minds["ana"].needs[Need.HUNGER] = 0.2
    assert economy.price(ana, home) == economy.price(ana, NOODLES) == 0
    assert economy.price(ana, CAFE) == shops["coffee_shop"].drink

    town.behaviour.minds["ana"].needs[Need.HUNGER] = 0.8
    assert economy.price(ana, home) == economy.config.groceries
    assert economy.price(ana, NOODLES) == shops["noodle_bar"].meal
    assert economy.price(ana, CAFE) == shops["coffee_shop"].drink + shops["coffee_shop"].meal

    town.behaviour.hooks.set(supply=lambda goal, need: 0.0 if goal == CAFE else 1.0)
    assert economy.price(ana, CAFE) == shops["coffee_shop"].drink
    town.world.bus.publish(Served("ana", "mia", "flat white", 30.0, False))
    assert economy.price(ana, CAFE) == 0


def test_work_pays_its_wage_or_reckoned_takings_an_hour() -> None:
    ana = resident("ana", workplace="park", pay=wage(18))
    bea = resident("bea", "house_2", workplace="noodle_bar", hours=(11, 21), pay=TAKINGS)
    town = Town([ana, bea])
    economy = town.economy

    assert economy.earnings(ana, Goal(A.WORK, "park")) == 18
    assert economy.earnings(ana, Goal(A.PARK, "park")) == 0
    assert economy.earnings(bea, Goal(A.WORK, "noodle_bar")) == economy.config.takings
    assert economy.money_of(ana) == 200


def test_shifts_are_on_time_late_or_skipped() -> None:
    lax = {
        "responsibility": 0.0,
        "money": 1000.0,
        "pay": wage(20),
        "workplace": "park",
        "hours": (9, 10),
    }
    npcs = [resident("ana", **lax), resident("bea", "house_2", **lax), resident("cy", **lax)]
    skipping = STEADY.model_copy(update={"skip": 1.0})
    town = Town(npcs, hour=8.5, config=skipping)
    grace = timedelta(minutes=town.economy.config.late)
    for npc in ("ana", "bea", "cy"):
        town.movement.place(npc, "park")
        town.stay(npc, Goal(A.PARK, "park"), minutes=600)

    town.run(minutes=33)
    town.stay("ana", Goal(A.WORK, "park"), minutes=600)
    town.run(minutes=17)
    town.stay("bea", Goal(A.WORK, "park"), minutes=600)
    town.run(minutes=50)

    turns = {turn.npc: turn for turn in town.economy.turns}
    ana, bea = turns["ana"], turns["bea"]
    assert ana.arrived is not None and ana.arrived - ana.start > timedelta(minutes=2)
    assert not ana.late(grace)
    assert bea.late(grace)
    assert "cy" not in turns or turns["cy"].arrived is None


def test_arriving_within_the_grace_is_on_time() -> None:
    start = THURSDAY + timedelta(hours=9)
    grace = timedelta(minutes=ECONOMY.late)

    def turn(minutes: float) -> Turn:
        return Turn("ana", start, start + timedelta(hours=4), start + timedelta(minutes=minutes))

    assert grace == timedelta(minutes=5)
    assert not turn(0).late(grace) and not turn(5).late(grace)
    assert turn(5.1).late(grace)
    assert not Turn("ana", start, start + timedelta(hours=4)).late(grace)


def test_a_shift_under_way_when_the_economy_starts_is_not_timed() -> None:
    town = Town([resident("ana", workplace="park", hours=(7, 12), pay=wage(20))], hour=9)

    town.run(minutes=1)

    assert town.economy.turns == []


def test_restoring_puts_back_saved_money_and_opens_the_ledger_on_it() -> None:
    town = Town([resident("ana"), resident("bea", "house_2")])
    town.economy.pay("ana", OUTSIDE, 10, Kind.RENT)

    town.economy.restore({"ana": 80.0, "zed": 5.0}, THURSDAY.date())

    assert town.economy.money == {"ana": 80.0, "bea": 200.0}
    assert town.economy.ledger.entries == []
    assert town.economy.ledger.opening == {"ana": 80.0, "bea": 200.0}
