import pytest

from simile.behaviour import Activity, Goal
from simile.cafe.cafe import Phase
from simile.cafe.config import DEFAULT_CONFIG as CAFE_CONFIG
from simile.cafe.events import GaveUp, Ordered, Served
from simile.cafe.orders import Exchange, Said
from simile.schema import Aspect, Npc
from simile.sim import ConversationEnded, ConversationStarted, LineSpoken
from simile.social import meet
from simile.world import Point

from .conftest import ANA, BEA, BEN, CAL, DAY, UPSTAIRS, Village, keen, make_npc, quiet_director

pytestmark = pytest.mark.anyio

COFFEE = keen(Activity.COFFEE_SHOP)
CAREFUL = CAFE_CONFIG.model_copy(update={"mistake": 0.0})
TILL = Point(5, 4, "coffee_shop")


async def test_the_barista_starts_at_the_till_when_the_cafe_opens() -> None:
    village = Village(start=DAY.replace(hour=6, minute=50))

    await village.run(minutes=5)
    assert not village.cafe.on_shift
    assert not village.behaviour.minds["bea"].held

    await village.run(minutes=10)
    assert village.cafe.on_shift
    assert village.at("bea") == TILL
    assert village.behaviour.goal("bea") == Goal(Activity.COFFEE_SHOP, "coffee_shop")


async def test_the_barista_finishes_at_closing_time() -> None:
    village = Village(start=DAY.replace(hour=16, minute=55))

    await village.run(minutes=2)
    assert village.cafe.on_shift

    await village.run(minutes=10)
    assert not village.cafe.on_shift
    assert village.behaviour.minds["bea"].held is None or village.cafe.going_home is not None


async def test_off_shift_the_barista_sleeps_upstairs_not_at_the_counter() -> None:
    village = Village(start=DAY.replace(hour=23, minute=30))

    await village.run(minutes=3)

    assert village.at("bea") == UPSTAIRS
    assert village.behaviour.goal("bea").activity is Activity.SLEEP
    assert not village.behaviour.minds["bea"].held


async def test_nobody_works_the_counter_without_a_barista() -> None:
    village = Village((ANA,), behaviour=COFFEE)

    await village.run(minutes=15)

    assert village.cafe.barista is None
    assert village.of(Ordered) == []


async def test_the_queue_is_served_in_the_order_people_join_it() -> None:
    village = Village((BEA, ANA, BEN, CAL), behaviour=COFFEE, config=CAREFUL)
    joined: list[str] = []

    def everyone_served() -> bool:
        joined.extend(npc for npc in village.cafe.queue if npc not in joined)
        return len(village.of(Served)) >= 3

    await village.run_until(everyone_served)

    assert sorted(joined) == ["ana", "ben", "cal"]
    assert [event.customer for event in village.of(Ordered)] == joined
    assert [event.customer for event in village.of(Served)] == joined


def all_at_once(village: Village) -> None:
    """Send the three customers in together from the terrace."""
    for npc in ("ana", "ben", "cal"):
        village.movement.place(npc, "cafe_terrace")
        village.behaviour.nudge(npc, Goal(Activity.COFFEE_SHOP, "coffee_shop"), 0.0)


async def test_the_queue_runs_down_the_lane_from_the_counter() -> None:
    village = Village((BEA, ANA, BEN, CAL), behaviour=COFFEE, config=CAREFUL)
    all_at_once(village)
    cafe = village.cafe
    longest = 0

    def lined_up() -> bool:
        nonlocal longest
        for n, npc in enumerate(cafe.queue):
            assert cafe.visits[npc].spot == cafe.spots[n]
        longest = max(longest, len(cafe.queue))
        return len(village.of(Served)) >= 3

    await village.run_until(lined_up)

    assert [(spot.x, spot.y) for spot in cafe.spots[:4]] == [(5, 6), (5, 7), (5, 8), (5, 9)]
    assert longest >= 2


async def test_a_residents_order_becomes_events_between_them_and_the_barista() -> None:
    village = Village((BEA, ANA), behaviour=COFFEE, config=CAREFUL)

    await village.run_until(lambda: bool(village.of(Served)))

    [served] = village.of(Served)
    history = village.store.shared_history("ana", "bea", village.now)
    assert {(event.actor, event.target) for event in history.events} == {
        ("bea", "ana"),
        ("ana", "bea"),
    }
    made = next(event for event in history.events if event.actor == "bea")
    assert made.action == f"made my {served.drink}" and made.valence > 0
    ana = village.store.relationship("ana", "bea")
    assert ana is not None and ana.like > meet(ANA, "bea").like and ana.familiarity > 0
    bea = village.store.relationship("bea", "ana")
    assert bea is not None and bea.familiarity > 0
    [memory] = village.store.recall("ana", village.now, about="bea")
    assert served.drink in memory.content and "Bea" in memory.content


async def test_the_wrong_drink_is_remade_and_costs_the_barista_respect() -> None:
    sloppy = CAFE_CONFIG.model_copy(update={"mistake": 1.0})
    village = Village((BEA, ANA), behaviour=COFFEE, config=sloppy)

    await village.run_until(lambda: bool(village.of(Served)))

    [served] = village.of(Served)
    assert served.wrong
    said = [event.line.text for event in village.of(LineSpoken) if event.line.speaker == "ana"]
    assert any("asked for" in text or "that's not" in text for text in said)
    history = village.store.shared_history("ana", "bea", village.now)
    [wrong] = [event for event in history.events if event.action == "got my order wrong"]
    assert wrong.aspects == [Aspect.RESPECT] and wrong.valence < 0


async def test_a_slow_wait_counts_against_the_barista() -> None:
    impatient = CAREFUL.model_copy(update={"slow": 1.0})
    village = Village((BEA, ANA), behaviour=COFFEE, config=impatient)

    await village.run_until(lambda: bool(village.of(Served)))

    history = village.store.shared_history("ana", "bea", village.now)
    assert any(event.action == "kept me waiting" for event in history.events)


async def test_someone_who_waits_too_long_gives_up() -> None:
    hasty = CAREFUL.model_copy(update={"patience": 20.0})
    village = Village((BEA, ANA, BEN, CAL), behaviour=COFFEE, config=hasty)
    all_at_once(village)

    await village.run_until(lambda: bool(village.of(GaveUp)))

    gave_up = village.of(GaveUp)[0]
    assert gave_up.customer not in village.cafe.queue
    history = village.store.shared_history(gave_up.customer, "bea", village.now)
    assert [event.action for event in history.events] == ["kept me waiting so long I gave up"]


async def test_someone_whose_walk_in_ends_short_of_the_cafe_is_let_go() -> None:
    village = Village((BEA, ANA), behaviour=COFFEE)
    await village.run_until(lambda: "ana" in village.cafe.visits)
    assert village.cafe.visits["ana"].phase is Phase.COMING

    village.movement.stop("ana")
    await village.run(seconds=0.3)

    assert "ana" not in village.cafe.visits
    assert not village.behaviour.minds["ana"].held
    assert village.at("ana").map == "village"


async def test_stock_orders_call_no_llm_and_start_no_conversation() -> None:
    village = Village((BEA, ANA), behaviour=COFFEE, config=CAREFUL)

    await village.run_until(lambda: bool(village.of(Served)))

    assert village.calls == []
    assert village.of(ConversationStarted) == []
    assert len([e for e in village.of(LineSpoken) if e.line.speaker == "bea"]) >= 2


async def test_an_order_is_a_written_conversation_when_the_director_would_nudge() -> None:
    exchange = Exchange(
        lines=[
            Said(by="barista", text="Morning, Ana. Long night?"),
            Said(by="customer", text="The longest. A double espresso, please."),
            Said(by="barista", text="Coming right up."),
        ],
        drink="double espresso",
        menu="espresso",
    )
    village = Village(
        (BEA, ANA),
        behaviour=COFFEE,
        config=CAREFUL,
        replies=[exchange],
        director=quiet_director(DAY.replace(hour=8)),
    )
    village.player_at_counter()

    await village.run_until(lambda: bool(village.of(Served)))

    [started] = village.of(ConversationStarted)
    assert sorted(started.conversation.participants) == ["ana", "bea"]
    [ended] = village.of(ConversationEnded)
    assert [line.text for line in ended.conversation.lines] == [
        line.text for line in exchange.lines
    ]
    assert [call.purpose for call in village.calls] == ["cafe-exchange"]
    [ordered] = village.of(Ordered)
    assert (ordered.drink, ordered.menu) == ("double espresso", "espresso")


async def test_a_failed_written_order_falls_back_to_stock_lines() -> None:
    village = Village(
        (BEA, ANA),
        behaviour=COFFEE,
        config=CAREFUL,
        replies=["not json", "still not json"],
        director=quiet_director(DAY.replace(hour=8)),
    )
    village.player_at_counter()

    await village.run_until(lambda: bool(village.of(Served)))

    assert village.of(ConversationStarted) == []
    [ordered] = village.of(Ordered)
    assert ordered.menu is not None


async def test_a_resident_who_was_just_served_sits_down_instead_of_queuing() -> None:
    lingering = CAREFUL.model_copy(update={"sit": 1.0})
    village = Village((BEA, ANA), behaviour=COFFEE, config=lingering)

    await village.run_until(lambda: bool(village.of(Served)))
    await village.run(minutes=45)

    assert len(village.of(Served)) == 1
    here = village.at("ana")
    seats = {(seat.x, seat.y) for seat in CAREFUL.seats}
    assert here.map == "coffee_shop" and (round(here.x), round(here.y)) in seats


async def test_the_barista_and_the_queue_leave_the_player_to_come_to_them() -> None:
    lingering = CAREFUL.model_copy(update={"sit": 1.0})
    village = Village((BEA, ANA), behaviour=COFFEE, config=lingering)
    alone = village.behaviour.leave_player_alone

    await village.run_until(lambda: "ana" in village.cafe.queue)
    assert {"bea", "ana"} <= alone

    await village.run_until(lambda: bool(village.of(Served)))
    await village.run(seconds=1)
    assert "ana" not in alone and "bea" in alone


async def test_residents_order_their_usual_most_of_the_time() -> None:
    sweet: Npc = make_npc("dot", "house_4", pleasure=1.0, optimism=1.0, adventure=1.0)
    village = Village((BEA, sweet), behaviour=COFFEE, config=CAREFUL)

    await village.run_until(lambda: bool(village.of(Ordered)))

    assert village.cafe.menu.usual(sweet).id == "hot_chocolate"
