from datetime import UTC, datetime, timedelta

import pytest

from simile.behaviour import Activity, Behaviour, Goal, Need
from simile.economy import PLAYER, Batch, Kind
from simile.economy.economy import Economy
from simile.memory import MemoryStore
from simile.npc import load_npcs
from simile.player.config import DEFAULT_CONFIG
from simile.player.hunger import DEFAULT_STARVING, Hunger
from simile.protocol import Meal, Shut, ShutReason
from simile.schema import (
    PLAYER_ID,
    Bionic,
    Body,
    Item,
    ItemKind,
    Npc,
    Pay,
    PayKind,
    Player,
    lamp,
)
from simile.sim import Clock, FakeWallClock, World
from simile.world import Movement, Point
from simile.world.map import load_maps
from simile.world.paths import Spot

MAPS = load_maps()
NOW = datetime(2026, 1, 1, 12, tzinfo=UTC)
ODALYS = load_npcs()[0].model_copy(
    update={
        "id": "odalys",
        "home": "house_3",
        "workplace": "noodle_bar",
        "pay": Pay(kind=PayKind.TAKINGS),
        "money": 100.0,
    }
)
BUN = Item(id="pork_bun", kind=ItemKind.FOOD, name="Pork bun", weight=0.2)
WIRE = Item(id="copper_wire", kind=ItemKind.SALVAGE, name="Copper wire", weight=1.5)
HOME = Point(13, 2, "maker_space_floor_0")
BED = Spot("maker_space_floor_2", 5, 2)
NOODLES = Meal(place="noodle_bar", name="Golden Bowl Noodles", price=10)


SHIFTS = next(npc for npc in load_npcs() if npc.id == "odalys").shifts
"""Tuesday to Sunday, 11:00 to 14:30 and 17:00 to 21:30."""
MONDAY = datetime(2026, 10, 26, tzinfo=UTC)


def monday(hour: float, days: int = 0) -> datetime:
    return MONDAY + timedelta(days=days, hours=hour)


class Village:
    def __init__(
        self, player: Player | None = None, now: datetime = NOW, keeper: Npc = ODALYS
    ) -> None:
        self.world = World(Clock(now), FakeWallClock())
        self.movement = Movement(MAPS, self.world.bus)
        behaviour = Behaviour(
            self.world.clock,
            self.world.bus,
            self.movement,
            [keeper],
            MemoryStore(":memory:"),
            seed=0,
        )
        self.player = player or Player()
        self.economy = Economy(self.world.clock, behaviour, player=self.player)
        self.open: set[str] = {"noodle_bar", "coffee_shop"}
        self.playing = True
        self.pangs: list[float] = []
        self.hunger = Hunger(
            self.player,
            self.movement,
            self.world.clock,
            supply=self.supply,
            economy=self.economy,
            playing=lambda: self.playing,
            pang=self.pangs.append,
        )

    def supply(self, goal: Goal, need: Need) -> float:
        assert need is Need.HUNGER
        return 1.0 if goal.target in self.open else 0.0

    def stand(self, x: float, y: float, map: str) -> None:
        self.movement.track(PLAYER_ID, Point(x, y, map))

    def here(self) -> Point:
        return self.movement.position(PLAYER_ID)


def test_hunger_rises_while_someone_is_playing() -> None:
    village = Village()

    village.hunger.tick(3600)
    assert village.player.hunger == pytest.approx(0.25)
    village.hunger.tick(1800)
    assert village.player.hunger == pytest.approx(0.375)


def test_hunger_waits_while_nobody_is_playing() -> None:
    village = Village(Player(hunger=0.5))
    village.playing = False

    village.hunger.tick(3600 * 24)

    assert village.player.hunger == 0.5


@pytest.mark.parametrize(
    ("x", "y", "map"),
    [(13, 2, "maker_space_floor_0"), (4, 2, "maker_space_floor_1"), (8, 2, "maker_space_floor_2")],
)
def test_a_meal_at_home_is_free_on_any_floor(x: int, y: int, map: str) -> None:
    village = Village(Player(hunger=0.8))
    village.stand(x, y, map)

    assert village.hunger.meal() == Meal(place="maker_space", name="home", price=0)
    assert village.hunger.eat(None)
    assert village.player.hunger == 0
    assert village.player.money == 0


def test_a_meal_at_the_noodle_bar_is_paid_to_its_keeper_and_taken_from_the_batch() -> None:
    village = Village(Player(money=25, hunger=0.9))
    economy = village.economy
    economy.batches["noodle_bar"] = Batch(shop="noodle_bar", shift=NOW, cooked=6, left=1)
    village.stand(9, 2, "noodle_bar_floor_1")

    assert village.hunger.meal() == NOODLES
    assert village.hunger.eat(None)

    assert village.player.hunger == 0
    assert village.player.money == 15
    assert economy.money["odalys"] == 100 + 10 - 3
    purchase = economy.ledger.entries[-2]
    assert (purchase.kind, purchase.payer, purchase.payee) == (Kind.PURCHASE, PLAYER, "odalys")
    assert (purchase.amount, purchase.place) == (10, "noodle_bar")
    assert economy.ledger.gap(economy.money) == 0
    assert economy.ledger.net(PLAYER) == village.player.money - 25
    batch = economy.batches["noodle_bar"]
    assert (batch.left, batch.sold_out) == (0, NOW)


def test_the_cafe_serves_a_lighter_meal_for_less() -> None:
    village = Village(Player(money=5, hunger=0.9))
    village.stand(9, 2, "coffee_shop_floor_1")

    assert village.hunger.meal() == Meal(place="coffee_shop", name="The Daily Grind", price=5)
    assert village.hunger.eat(None)
    assert (village.player.money, village.player.hunger) == (0, pytest.approx(0.4))


def test_no_meal_at_a_shop_that_would_not_feed_a_resident() -> None:
    village = Village(Player(money=25, hunger=0.9))
    village.open = set()
    village.stand(9, 2, "noodle_bar_floor_1")

    assert village.hunger.meal() is None
    assert not village.hunger.eat(None)
    assert (village.player.money, village.player.hunger) == (25, 0.9)


def test_the_noodle_bar_feeds_them_only_while_its_keeper_is_in_and_it_has_meals_left() -> None:
    village = Village(Player(money=25, hunger=0.9))
    economy, behaviour = village.economy, village.economy.behaviour
    village.hunger.supply = economy.supply
    behaviour.start()
    village.stand(9, 2, "noodle_bar_floor_1")
    assert village.hunger.meal() is None

    work = Goal(Activity.WORK, "noodle_bar")
    behaviour.restore("odalys", work, behaviour.needs("odalys"), NOW, None, {})
    economy.batches["noodle_bar"] = Batch(shop="noodle_bar", shift=NOW, cooked=6, left=1)
    assert economy.staffed("noodle_bar")
    assert village.hunger.eat(None)

    assert village.hunger.meal() is None
    assert not village.hunger.eat(None)
    assert village.player.money == 15


def test_no_meal_they_cannot_pay_for() -> None:
    village = Village(Player(money=9.5, hunger=0.9))
    village.stand(9, 2, "noodle_bar_floor_1")

    assert village.hunger.meal() == NOODLES
    assert not village.hunger.eat(None)
    assert (village.player.money, village.player.hunger) == (9.5, 0.9)
    assert village.economy.ledger.entries == []


@pytest.mark.parametrize(
    ("x", "y", "map"),
    [(70, 15, "high_street"), (3, 2, "house_3_floor_0"), (5, 2, "gallery_floor_0")],
)
def test_no_meal_anywhere_else(x: int, y: int, map: str) -> None:
    village = Village(Player(money=25, hunger=0.9))
    village.stand(x, y, map)

    assert village.hunger.meal() is None
    assert not village.hunger.eat(None)


def test_no_meal_before_the_server_knows_where_they_are() -> None:
    village = Village(Player(hunger=0.9))

    assert village.hunger.meal() is None
    assert not village.hunger.eat(None)


def test_eating_food_they_carry_relieves_it_and_uses_it_up() -> None:
    village = Village(Player(items=[lamp(), BUN, WIRE, BUN], hunger=0.9))

    assert village.hunger.eat("pork_bun")

    assert village.player.hunger == pytest.approx(0.5)
    assert village.player.items == [lamp(), WIRE, BUN]


@pytest.mark.parametrize("item", ["lamp", "copper_wire", "noodles"])
def test_only_food_they_carry_can_be_eaten(item: str) -> None:
    village = Village(Player(items=[lamp(), WIRE], hunger=0.9))

    assert not village.hunger.eat(item)
    assert village.player.items == [lamp(), WIRE]
    assert village.player.hunger == 0.9


def test_eating_never_takes_hunger_below_nothing() -> None:
    village = Village(Player(items=[BUN], hunger=0.1))

    assert village.hunger.eat("pork_bun")
    assert village.player.hunger == 0


def test_hunger_stops_at_starving_and_hurts_every_twelve_sim_minutes() -> None:
    village = Village(Player(hunger=1.0))

    village.hunger.tick(11 * 60)
    assert village.player.hunger == 1
    assert village.pangs == []
    village.hunger.tick(60)
    assert village.pangs == [DEFAULT_STARVING.damage]
    village.hunger.tick(2 * DEFAULT_STARVING.every * 3600)
    assert village.pangs == [DEFAULT_STARVING.damage] * 3
    assert village.player.hunger == 1


def test_from_fed_to_starved_to_death_takes_six_sim_hours() -> None:
    assert 1 / DEFAULT_CONFIG.rise == 4
    assert round(1 / DEFAULT_STARVING.damage) * DEFAULT_STARVING.every == pytest.approx(2)


def test_eating_stops_the_pangs_and_starts_their_count_again() -> None:
    village = Village(Player(hunger=1.0, items=[lamp(), BUN]))
    village.hunger.tick(11 * 60)

    assert village.hunger.eat("pork_bun")
    village.hunger.tick(11 * 60)
    assert village.pangs == []
    assert village.player.hunger < 1

    village.player.hunger = 1.0
    village.hunger.tick(11 * 60)
    assert village.pangs == []
    village.hunger.tick(60)
    assert village.pangs == [DEFAULT_STARVING.damage]


def test_a_pang_that_wakes_them_fed_stops_the_rest_of_the_tick() -> None:
    village = Village(Player(hunger=1.0))

    def killed(damage: float) -> None:
        village.pangs.append(damage)
        village.player.hunger = DEFAULT_CONFIG.waking

    village.hunger.pang = killed
    village.hunger.tick(3600)

    assert village.pangs == [DEFAULT_STARVING.damage]


def test_nothing_hurts_while_nobody_is_playing() -> None:
    village = Village(Player(hunger=1.0))
    village.playing = False

    village.hunger.tick(3600)

    assert village.pangs == []


def test_a_power_cell_ends_starving() -> None:
    village = Village(Player(hunger=1.0, body=Body(stomach=Bionic.POWER_CELL)))

    village.hunger.tick(3600)

    assert village.player.hunger == 0
    assert village.pangs == []


def test_a_power_cell_clears_hunger_and_takes_meals_off_the_menu() -> None:
    cell = Body(stomach=Bionic.POWER_CELL)
    village = Village(Player(items=[lamp(), BUN], hunger=0.6, body=cell))
    village.stand(13, 2, "maker_space_floor_0")

    village.hunger.tick(3600)

    assert village.player.hunger == 0
    assert village.hunger.meal() is None
    assert not village.hunger.eat(None)
    assert not village.hunger.eat("pork_bun")
    assert village.player.items == [lamp(), BUN]


def at_the_noodle_bar(now: datetime) -> Village:
    """With Odalys's own shifts, and the economy saying whether it's serving."""
    village = Village(
        Player(money=25, hunger=0.9), now, ODALYS.model_copy(update={"shifts": SHIFTS})
    )
    village.hunger.supply = village.economy.supply
    village.economy.behaviour.start()
    village.stand(9, 2, "noodle_bar_floor_1")
    return village


def test_the_noodle_bar_is_shut_on_a_monday_and_opens_on_tuesday() -> None:
    village = at_the_noodle_bar(monday(19 + 52 / 60))

    assert village.hunger.meal() is None
    assert village.hunger.shut() == Shut(
        place="noodle_bar",
        name="Golden Bowl Noodles",
        reason=ShutReason.CLOSED,
        opens=monday(11, days=1),
    )


def test_after_its_last_shift_on_sunday_it_opens_again_on_tuesday() -> None:
    shut = at_the_noodle_bar(monday(22, days=6)).hunger.shut()

    assert shut is not None
    assert (shut.reason, shut.opens) == (ShutReason.CLOSED, monday(11, days=8))


def test_after_the_evening_shift_it_opens_for_lunch_the_next_day() -> None:
    shut = at_the_noodle_bar(monday(23, days=5)).hunger.shut()

    assert shut is not None
    assert shut.opens == monday(11, days=6)


def test_while_its_keeper_is_late_it_opens_at_their_next_shift() -> None:
    shut = at_the_noodle_bar(monday(11 + 20 / 60, days=1)).hunger.shut()

    assert shut is not None
    assert (shut.reason, shut.opens) == (ShutReason.CLOSED, monday(17, days=1))


def test_sold_out_while_its_keeper_is_in_until_the_next_shift() -> None:
    now = monday(13, days=1)
    village = at_the_noodle_bar(now)
    behaviour = village.economy.behaviour
    work = Goal(Activity.WORK, "noodle_bar")
    behaviour.restore("odalys", work, behaviour.needs("odalys"), now, None, {})
    batch = Batch(shop="noodle_bar", shift=monday(11, days=1), cooked=6, left=0, sold_out=now)
    village.economy.batches["noodle_bar"] = batch

    assert village.hunger.meal() is None
    shut = village.hunger.shut()
    assert shut is not None
    assert (shut.reason, shut.opens) == (ShutReason.SOLD_OUT, monday(17, days=1))


def test_a_shop_that_is_serving_has_a_meal_and_is_not_shut() -> None:
    village = Village(Player(money=25, hunger=0.9))
    village.stand(9, 2, "noodle_bar_floor_1")

    assert village.hunger.meal() == NOODLES
    assert village.hunger.shut() is None


def test_after_last_orders_the_cafe_opens_the_next_morning() -> None:
    mirela = next(npc for npc in load_npcs() if npc.id == "mirela")
    village = Village(Player(money=25, hunger=0.9), monday(17.5), mirela)
    village.open = set()
    village.stand(9, 2, "coffee_shop_floor_1")

    assert village.hunger.shut() == Shut(
        place="coffee_shop",
        name="The Daily Grind",
        reason=ShutReason.CLOSED,
        opens=monday(7, days=1),
    )


@pytest.mark.parametrize(
    ("x", "y", "map"),
    [(13, 2, "maker_space_floor_0"), (70, 15, "high_street"), (3, 2, "house_3_floor_0")],
)
def test_nowhere_else_is_shut(x: int, y: int, map: str) -> None:
    village = Village(Player(hunger=0.9))
    village.open = set()
    village.stand(x, y, map)

    assert village.hunger.shut() is None


def test_nothing_is_shut_to_them_on_a_power_cell() -> None:
    village = Village(Player(body=Body(stomach=Bionic.POWER_CELL)))
    village.open = set()
    village.stand(9, 2, "noodle_bar_floor_1")

    assert village.hunger.shut() is None
