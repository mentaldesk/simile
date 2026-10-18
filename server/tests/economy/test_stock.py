from datetime import timedelta

import pytest

from simile.behaviour import Activity, Goal, Need, Situation, score
from simile.economy import DEFAULT_CONFIG as ECONOMY
from simile.economy import OUTSIDE, Batch, Kind
from simile.economy.stock import stocked
from simile.schema import CoreValue, Npc
from simile.world import Point

from .test_economy import NOODLES, STEADY, TAKINGS, Town, resident

A = Activity
HOME = Goal(A.HOME, "house_1")
BATCH = ECONOMY.shops["noodle_bar"].batch


def cook(money: float = 1000.0, **values: float) -> Npc:
    return resident(
        "cook",
        "house_2",
        workplace="noodle_bar",
        hours=(11, 21),
        pay=TAKINGS,
        money=money,
        **values,
    )


def at_work(town: Town, minutes: float = 600) -> None:
    town.movement.place("cook", "noodle_bar")
    town.stay("cook", Goal(A.WORK, "noodle_bar"), minutes=minutes)
    town.run(minutes=0.2)


def hunger_term(town: Town, goal: Goal) -> float:
    """What hunger adds to `goal`'s score for Ana, with the economy saying what's there."""

    def at(level: float) -> float:
        values = {value: 0.5 for value in CoreValue}
        needs = {need: 0.0 for need in Need} | {Need.HUNGER: level}
        here = Point(31, 22)
        situation = Situation(
            values, needs, 12.0, here, "house_1", 22.5, supply=town.economy.supply
        )
        return score(goal, situation, town.behaviour.places, town.behaviour.config)

    return at(0.9) - at(0.0)


def test_a_shut_or_sold_out_noodle_bar_scores_nothing_for_hunger() -> None:
    town = Town([resident("ana"), cook()], hour=12)
    assert hunger_term(town, NOODLES) == 0.0

    at_work(town)
    assert hunger_term(town, NOODLES) > 0.5

    town.economy.batches["noodle_bar"].left = 0
    assert hunger_term(town, NOODLES) == 0.0
    assert hunger_term(town, HOME) > 0.5


def test_the_cook_cooks_a_batch_on_arriving_and_whats_left_goes_off_at_closing() -> None:
    town = Town([cook()], hour=20.5)
    at_work(town, minutes=30)

    [batch] = town.economy.cooked
    assert (batch.shop, batch.shift.hour, batch.cooked, batch.left) == (
        "noodle_bar",
        11,
        BATCH,
        BATCH,
    )
    assert town.economy.serving("noodle_bar")

    town.until(lambda: not town.economy.staffed("noodle_bar"), hours=2)
    town.run(minutes=0.2)

    assert (batch.left, batch.gone_off) == (0, BATCH)
    assert not town.economy.serving("noodle_bar")


def test_the_last_meal_is_eaten_and_then_the_noodle_bar_has_sold_out() -> None:
    town = Town([resident("ana"), resident("bea", "house_3"), cook()], hour=12)
    at_work(town)
    town.economy.batches["noodle_bar"].left = 1
    town.movement.place("ana", "noodle_bar")
    town.stay("ana", NOODLES, hunger=0.85)

    town.run(minutes=10)

    batch = town.economy.batches["noodle_bar"]
    assert batch.left == 0 and batch.sold_out is not None
    assert town.behaviour.needs("ana")[Need.HUNGER] < 0.6
    town.movement.place("bea", "noodle_bar")
    town.stay("bea", NOODLES, hunger=0.85)
    town.run(minutes=10)
    assert town.behaviour.needs("bea")[Need.HUNGER] > 0.85
    bought = [e.amount for e in town.economy.ledger.entries if e.payer == "bea"]
    assert bought == [ECONOMY.shops["noodle_bar"].drink]


def test_a_skipped_shift_shuts_the_noodle_bar_and_its_cook_takes_nothing() -> None:
    skipping = STEADY.model_copy(update={"skip": 1.0})
    town = Town([resident("ana"), cook(responsibility=0.0)], hour=12, config=skipping)
    town.movement.place("ana", "noodle_bar")
    town.stay("ana", NOODLES, hunger=0.85)

    town.run(minutes=10)

    assert not town.economy.staffed("noodle_bar")
    assert town.economy.cooked == []
    assert town.behaviour.needs("ana")[Need.HUNGER] > 0.85
    assert not any(e.payee == "cook" for e in town.economy.ledger.entries)


def test_the_noodle_bar_stays_open_while_its_cook_takes_a_break_mid_shift() -> None:
    town = Town([cook()], hour=12)
    at_work(town)

    town.movement.place("cook", "park")
    town.stay("cook", Goal(A.PARK, "park"), minutes=30)
    town.run(minutes=1)

    assert not town.behaviour.working("cook")
    assert town.economy.staffed("noodle_bar")


def test_a_meal_at_home_comes_out_of_the_fridge() -> None:
    town = Town([resident("ana")], hour=11)
    town.economy.fridges["house_1"] = 5
    town.movement.place("ana", "house_1")
    town.stay("ana", HOME, hunger=0.85)

    town.run(minutes=10)

    assert town.economy.fridges["house_1"] == 4
    assert town.economy.ledger.entries == []


def test_someone_at_home_fills_a_low_fridge_through_the_ledger() -> None:
    town = Town([resident("ana")], hour=11)
    town.economy.fridges["house_1"] = ECONOMY.low
    town.movement.place("ana", "house_1")
    town.stay("ana", HOME, hunger=0.2)

    town.run(minutes=1)

    [order] = town.economy.ledger.entries
    meals = ECONOMY.fridge - ECONOMY.low
    assert (order.kind, order.payer, order.payee) == (Kind.GROCERIES, "ana", OUTSIDE)
    assert order.amount == pytest.approx(meals * ECONOMY.groceries)
    assert town.economy.fridges["house_1"] == ECONOMY.fridge


def test_nobody_orders_groceries_while_out_or_asleep() -> None:
    town = Town([resident("ana")], hour=3)
    town.economy.fridges["house_1"] = 0

    town.run(minutes=1)
    assert town.behaviour.goal("ana").activity is A.SLEEP

    town.world.clock.now += timedelta(hours=8)
    town.movement.place("ana", "park")
    town.stay("ana", Goal(A.PARK, "park"), hunger=0.1)
    town.run(minutes=1)

    assert town.economy.ledger.entries == []


def test_an_empty_fridge_sends_a_hungry_resident_out_to_eat() -> None:
    town = Town([resident("ana"), cook()], hour=12)
    at_work(town)
    town.economy.fridges["house_1"] = 0
    assert hunger_term(town, HOME) == 0.0

    town.movement.place("ana", "square")
    town.stay("ana", Goal(A.SQUARE, "square"), minutes=0, hunger=0.85)
    town.run(minutes=0.2)

    assert town.behaviour.goal("ana") == NOODLES


def test_an_empty_fridge_at_home_is_filled_and_then_they_eat() -> None:
    town = Town([resident("ana")], hour=21)
    town.economy.fridges["house_1"] = 0
    town.movement.place("ana", "house_1")
    town.stay("ana", HOME, hunger=0.85)

    town.run(minutes=10)

    assert [e.kind for e in town.economy.ledger.entries] == [Kind.GROCERIES]
    assert town.economy.fridges["house_1"] == ECONOMY.fridge - 1
    assert town.behaviour.needs("ana")[Need.HUNGER] < 0.85


def test_fridges_start_partly_full_and_differ_between_homes() -> None:
    levels = {stocked(f"house_{n}", ECONOMY) for n in range(1, 11)}

    assert all(ECONOMY.low < level <= ECONOMY.fridge for level in levels)
    assert len(levels) > 1
    assert stocked("house_1", ECONOMY) == stocked("house_1", ECONOMY)


def test_the_noodle_bar_sells_a_drink_to_whoever_comes_in_while_its_staffed() -> None:
    town = Town([resident("ana"), cook()], hour=10.5)
    drink = ECONOMY.shops["noodle_bar"].drink
    town.movement.place("ana", "noodle_bar")
    town.stay("ana", NOODLES, minutes=20, hunger=0.2)
    town.run(minutes=1)
    assert town.economy.ledger.entries == []

    at_work(town)
    town.run(minutes=1)
    assert town.economy.money["ana"] == pytest.approx(200 - drink)

    town.stay("ana", NOODLES, minutes=20, hunger=0.2)
    town.run(minutes=1)
    assert town.economy.money["ana"] == pytest.approx(200 - drink)
    assert town.economy.price(town.behaviour.npcs["ana"], NOODLES) == 0


def test_a_batch_restored_mid_shift_is_not_cooked_again() -> None:
    town = Town([cook()], hour=12)
    shift = town.now.replace(hour=11)
    batch = Batch(shop="noodle_bar", shift=shift, cooked=BATCH, left=2)
    town.economy.restore({}, town.now.date(), {}, {"noodle_bar": batch})

    at_work(town)

    assert town.economy.cooked == []
    assert town.economy.batches["noodle_bar"].left == 2
    assert town.economy.fridges["house_2"] == stocked("house_2", ECONOMY)
