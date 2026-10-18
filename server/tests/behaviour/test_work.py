from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from simile.behaviour import DEFAULT_CONFIG, Activity, Behaviour, Goal, Need, Places, Situation
from simile.behaviour.scoring import (
    Work,
    finances,
    punctuality,
    savings,
    score,
    skip_chance,
    spending,
    thrift,
)
from simile.memory import MemoryStore
from simile.npc import load_npcs
from simile.schema import CoreValue, Npc, Pay, PayKind, Shift, Weekday
from simile.sim import STEP, Clock, FakeWallClock, World
from simile.world import Movement, Point
from simile.world.map import load_maps, with_every_location

MAPS = load_maps()
PLACES = Places(with_every_location(MAPS))
TEMPLATE = load_npcs()[0]
THURSDAY = datetime(2026, 1, 1, tzinfo=UTC)
STEADY = DEFAULT_CONFIG.model_copy(update={"temperature": 0.0, "set_off_jitter": 0.0})
A = Activity
V = CoreValue
PARK_WORK = Goal(A.WORK, "park")
NOODLES = Goal(A.NOODLE_BAR, "noodle_bar")
NEUTRAL = dict.fromkeys(CoreValue, 0.5)


def worker(
    id: str,
    home: str = "house_1",
    workplace: str | None = "park",
    hours: tuple[float, float] = (10, 14),
    pay: Pay | None = None,
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
            "pay": pay or Pay(kind=PayKind.WAGE, amount=20),
            "values": scores,
            "craft": None,
        }
    )


class Village:
    def __init__(self, npcs: list[Npc], *, hour: float, config=STEADY, money=None) -> None:
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
        if money is not None:
            self.behaviour.hooks.set(money=lambda npc: money.get(npc.id))
        self.world.loop.register(self.behaviour)
        self.world.loop.register(self.movement)
        self.behaviour.start()

    @property
    def now(self) -> datetime:
        return self.world.clock.now

    def run(self, *, minutes: float) -> None:
        for _ in range(round(minutes * 60 / STEP)):
            self.world.loop.tick()

    def until(self, done: Callable[[], bool], *, minutes: float = 120) -> None:
        end = self.now + timedelta(minutes=minutes)
        while not done():
            assert self.now < end, "ran out of time"
            self.world.loop.tick()

    def stay(self, npc: str, goal: Goal, minutes: float = 60, **needs: float) -> None:
        mind = self.behaviour.minds[npc]
        levels = {**mind.needs, **{Need(need): level for need, level in needs.items()}}
        self.behaviour.restore(
            npc, goal, levels, self.now, self.now + timedelta(minutes=minutes), {}
        )


def situation(goal_work: Work | None = None, **changes: object) -> Situation:
    needs = dict.fromkeys(Need, 0.2) | {Need.FINANCES: 0.0}
    fields = {
        "values": NEUTRAL,
        "needs": needs,
        "hour": 12.0,
        "position": Point(30, 20),
        "home": "house_1",
        "bedtime": 22.5,
        "work": goal_work,
    }
    return Situation(**(fields | changes))  # type: ignore[arg-type]


def test_security_raises_the_savings_target_and_pleasure_spends_freely() -> None:
    assert savings(NEUTRAL) == DEFAULT_CONFIG.savings
    assert (
        savings(NEUTRAL | {V.SECURITY: 0.9})
        > savings(NEUTRAL)
        > savings(NEUTRAL | {V.SECURITY: 0.1})
    )
    assert (
        thrift(NEUTRAL | {V.PLEASURE: 0.9})
        < thrift(NEUTRAL)
        == 1
        < thrift(NEUTRAL | {V.PLEASURE: 0.1})
    )


def test_finances_are_how_far_below_the_target_they_are() -> None:
    assert finances(150, 300) == 0.5
    assert finances(450, 300) == 0
    assert finances(-20, 300) == 1


def test_a_price_hurts_more_the_shorter_they_are_and_still_counts_when_broke() -> None:
    price = 0.03

    comfortable, short, broke = (spending(level, price) for level in (0.0, 0.5, 1.0))

    assert comfortable < 0.1 * short < short < broke
    assert broke > 0


def test_an_option_that_costs_money_scores_less_for_someone_short_of_it() -> None:
    def noodles(level: float, price: float) -> float:
        needs = dict.fromkeys(Need, 0.2) | {Need.FINANCES: level}
        return score(
            NOODLES, situation(needs=needs, price=lambda goal: price), PLACES, DEFAULT_CONFIG
        )

    assert noodles(0.0, 0) - noodles(0.0, 8) < 0.05
    assert noodles(0.8, 8) < noodles(0.8, 0) - 0.5


def test_a_shift_pulls_hard_and_staying_on_draws_the_ambitious_and_the_short() -> None:
    on = situation(Work("park", True, 4.0))
    after = situation(Work("park", False, 0.875), earnings=lambda goal: 20.0)

    assert score(PARK_WORK, on, PLACES) - score(PARK_WORK, after, PLACES) > 1.5
    ambitious = situation(
        Work("park", False, 0.875), values=NEUTRAL | {V.AMBITION: 0.9, V.SUCCESS: 0.9}
    )
    assert score(PARK_WORK, ambitious, PLACES) > score(PARK_WORK, after, PLACES) + 0.5
    short = dict.fromkeys(Need, 0.2) | {Need.FINANCES: 0.6}
    broke = situation(Work("park", False, 0.875), needs=short, earnings=lambda goal: 20.0)
    assert score(PARK_WORK, broke, PLACES) > score(PARK_WORK, after, PLACES) + 0.5


def test_work_is_on_offer_only_when_they_have_somewhere_to_be() -> None:
    from simile.behaviour.scoring import candidates

    assert PARK_WORK not in candidates(situation(), PLACES)
    assert PARK_WORK in candidates(situation(Work("park", True, 3.0)), PLACES)


def test_discipline_sets_punctuality_and_responsibility_skipping() -> None:
    assert punctuality(NEUTRAL | {V.DISCIPLINE: 0.9}) > 0 == punctuality(NEUTRAL)
    assert punctuality(NEUTRAL | {V.DISCIPLINE: 0.1}) < 0

    assert skip_chance(NEUTRAL | {V.RESPONSIBILITY: 0.9}, 0.0) == 0
    lax = skip_chance(NEUTRAL | {V.RESPONSIBILITY: 0.1}, 0.0)
    assert 0 < lax <= DEFAULT_CONFIG.skip
    assert skip_chance(NEUTRAL | {V.RESPONSIBILITY: 0.1}, 0.5) == pytest.approx(lax / 2)


def test_they_set_off_for_a_shift_and_work_until_it_ends() -> None:
    village = Village([worker("ana", hours=(10, 14))], hour=9)
    village.movement.place("ana", "house_1")
    village.stay("ana", Goal(A.HOME, "house_1"), minutes=600)

    village.until(lambda: village.behaviour.working("ana"))
    assert THURSDAY + timedelta(hours=9.5) < village.now < THURSDAY + timedelta(hours=10, minutes=1)
    mind = village.behaviour.minds["ana"]
    assert mind.until == THURSDAY + timedelta(hours=14)

    village.run(minutes=60)
    assert village.behaviour.working("ana")


def test_the_disciplined_arrive_on_time_and_the_undisciplined_late() -> None:
    npcs = [
        worker("ana", hours=(10, 14), discipline=0.9),
        worker("bea", "house_2", hours=(10, 14), discipline=0.05),
    ]
    village = Village(npcs, hour=9)
    for npc, home in (("ana", "house_1"), ("bea", "house_2")):
        village.movement.place(npc, home)
        village.stay(npc, Goal(A.HOME, home), minutes=600)

    village.until(lambda: village.now >= THURSDAY + timedelta(hours=10, minutes=1))

    assert village.behaviour.working("ana")
    assert not village.behaviour.working("bea")
    village.until(lambda: village.behaviour.working("bea"), minutes=30)


def test_an_urgent_need_wins_over_a_shift() -> None:
    village = Village([worker("ana", hours=(10, 14))], hour=10.02)
    assert village.behaviour.minds["ana"].shift.set_off < village.now
    village.movement.place("ana", "park")
    village.stay("ana", Goal(A.PARK, "park"), minutes=600, hunger=0.97)

    village.run(minutes=0.2)

    mind = village.behaviour.minds["ana"]
    assert str(PARK_WORK) in mind.options
    assert mind.goal.activity in (A.HOME, A.NOODLE_BAR, A.COFFEE_SHOP)
    assert max(mind.options.values()) > mind.options[str(PARK_WORK)]


def test_someone_who_skips_a_shift_isnt_pulled_to_it() -> None:
    always = STEADY.model_copy(update={"skip": 1.0})
    village = Village([worker("ana", hours=(10, 14), responsibility=0.0)], hour=9.5, config=always)

    village.run(minutes=50)

    assert village.behaviour.minds["ana"].shift.skipping
    assert not village.behaviour.working("ana")


def test_they_decide_once_a_day_whether_to_skip_both_halves_of_a_split_shift() -> None:
    split = [
        Shift(days=list(Weekday), start=11, end=14.5),
        Shift(days=list(Weekday), start=17, end=21.5),
    ]
    cook = worker("ana", workplace="noodle_bar", responsibility=0.25).model_copy(
        update={"shifts": split}
    )
    village = Village([cook], hour=10, config=STEADY.model_copy(update={"skip": 1.0}))
    days: dict[object, set[bool]] = {}

    for day in range(12):
        for hour in (10, 15):
            village.world.clock.now = THURSDAY + timedelta(days=day, hours=hour)
            village.run(minutes=0.1)
            due = village.behaviour.minds["ana"].shift
            days.setdefault(due.start.date(), set()).add(due.skipping)

    assert all(len(skipped) == 1 for skipped in days.values())
    assert {next(iter(skipped)) for skipped in days.values()} == {True, False}


def test_a_talk_at_work_pauses_it_and_they_go_back_to_it() -> None:
    village = Village([worker("ana", hours=(10, 14))], hour=10.5)
    village.movement.place("ana", "park")
    village.stay("ana", PARK_WORK, minutes=300)
    village.run(minutes=1)

    village.behaviour.pause("ana", "player")
    village.run(minutes=3)
    village.behaviour.resume("ana")
    village.run(minutes=0.1)

    mind = village.behaviour.minds["ana"]
    assert mind.goal == PARK_WORK
    assert mind.until == THURSDAY + timedelta(hours=14)


def test_a_resident_restored_mid_stay_finishes_it_before_a_shift_under_way() -> None:
    village = Village([worker("ana", hours=(10, 14))], hour=10.5)
    village.movement.place("ana", "park")
    village.stay("ana", Goal(A.PARK, "park"), minutes=10)

    village.run(minutes=5)
    assert village.behaviour.goal("ana") == Goal(A.PARK, "park")

    village.until(lambda: village.behaviour.working("ana"), minutes=15)


def test_a_shift_gets_them_up_before_they_would_wake() -> None:
    late = worker("ana", hours=(7, 12), discipline=0.5, pleasure=1.0, peace_of_mind=1.0)
    village = Village([late], hour=4)
    assert village.behaviour.minds["ana"].wake > 7

    village.until(lambda: village.behaviour.goal("ana").activity is not A.SLEEP, minutes=240)

    assert village.now < THURSDAY + timedelta(hours=7)


def test_someone_working_from_home_is_at_home_but_a_shopkeeper_who_lives_upstairs_isnt() -> None:
    remote = worker("ana", workplace="house_1", hours=(9, 17))
    barista = worker("bea", "coffee_shop", workplace="coffee_shop", hours=(7, 17))
    village = Village([remote, barista, worker("cy", "house_3", workplace=None)], hour=11)
    village.movement.place("ana", "house_1")
    village.movement.place("bea", "coffee_shop")
    village.stay("ana", Goal(A.WORK, "house_1"), minutes=300)
    village.stay("bea", Goal(A.WORK, "coffee_shop"), minutes=300)

    assert not village.behaviour.available("cy", "ana")
    assert village.behaviour.available("cy", "bea")


def test_finances_follow_their_money_and_show_once_money_is_in_play() -> None:
    village = Village([worker("ana")], hour=11, money={"ana": 150.0})
    village.run(minutes=0.1)

    assert village.behaviour.needs("ana")[Need.FINANCES] == pytest.approx(0.5)
    state = village.behaviour.state("ana")
    assert state["money"] == 150.0
    assert state["needs"]["finances"] == 0.5  # type: ignore[index]
    assert state["shift"] is not None
