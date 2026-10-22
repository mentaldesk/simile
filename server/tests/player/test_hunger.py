from datetime import UTC, datetime

import pytest

from simile.behaviour import Activity, Behaviour, Goal, Need
from simile.economy import OUTSIDE, Batch, Kind
from simile.economy.economy import Economy
from simile.memory import MemoryStore
from simile.npc import load_npcs
from simile.player.hunger import Hunger
from simile.protocol import Meal
from simile.schema import PLAYER_ID, Item, ItemKind, MapTile, Pay, PayKind, Pile, Player, lamp
from simile.sim import Clock, FakeWallClock, World
from simile.world import Movement, Point
from simile.world.map import load_maps

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
SERVO = Item(id="servo_motor", kind=ItemKind.SALVAGE, name="Servo motor", weight=3.0)
HOME = Point(13, 2, "maker_space_floor_0")
NOODLES = Meal(place="noodle_bar", name="Golden Bowl Noodles", price=10)


class Village:
    def __init__(self, player: Player | None = None) -> None:
        self.world = World(Clock(NOW), FakeWallClock())
        self.movement = Movement(MAPS, self.world.bus)
        behaviour = Behaviour(
            self.world.clock,
            self.world.bus,
            self.movement,
            [ODALYS],
            MemoryStore(":memory:"),
            seed=0,
        )
        self.economy = Economy(self.world.clock, behaviour)
        self.open: set[str] = {"noodle_bar", "coffee_shop"}
        self.playing = True
        self.woke: list[MapTile] = []
        self.player = player or Player()
        self.hunger = Hunger(
            self.player,
            self.movement,
            self.world.clock,
            supply=self.supply,
            economy=self.economy,
            playing=lambda: self.playing,
            collapsed=self.woke.append,
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
    assert (purchase.kind, purchase.payer, purchase.payee) == (Kind.PURCHASE, OUTSIDE, "odalys")
    assert (purchase.amount, purchase.place) == (10, "noodle_bar")
    assert economy.ledger.gap(economy.money) == 0
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


def test_starving_collapses_them_at_home_with_what_they_carried_left_where_they_fell() -> None:
    village = Village(Player(items=[lamp(), WIRE], hunger=0.999))
    village.stand(12.3, 15, "kapok_walk")

    village.hunger.tick(60)

    assert village.player.hunger == 0.75
    assert village.player.items == []
    assert village.player.left == [
        Pile(at=MapTile(map="kapok_walk", x=12, y=15), items=[lamp(), WIRE])
    ]
    assert village.here() == HOME
    assert village.woke == [MapTile(map="maker_space_floor_0", x=13, y=2)]


@pytest.mark.parametrize(
    ("x", "y", "ground"),
    [(17.2, 5.6, (17, 8)), (22.4, 5, (22, 15)), (3, 13.5, (3, 15))],
    ids=["over_a_roof", "over_a_gap", "on_a_ladder"],
)
def test_what_they_carried_falls_to_the_ground_below(
    x: float, y: float, ground: tuple[int, int]
) -> None:
    village = Village(Player(hunger=1 - 1e-9))
    village.stand(x, y, "rooftops")

    village.hunger.tick(1)

    fell = MapTile(map="rooftops", x=ground[0], y=ground[1])
    assert village.player.left == [Pile(at=fell, items=[lamp()])]


def test_collapsing_with_nothing_on_them_leaves_nothing() -> None:
    village = Village(Player(items=[], hunger=0.9999))
    village.stand(70, 15, "high_street")

    village.hunger.collapse()

    assert village.player.left == []
    assert village.here() == HOME


def test_each_collapse_leaves_another_pile_after_the_last() -> None:
    village = Village()
    village.stand(70, 15, "high_street")
    village.hunger.collapse()
    village.player.items = [BUN]
    village.stand(30, 15, "lychee_lane")

    village.hunger.collapse()

    assert [pile.at for pile in village.player.left] == [
        MapTile(map="high_street", x=70, y=15),
        MapTile(map="lychee_lane", x=30, y=15),
    ]


def test_a_collapse_before_the_server_knows_where_they_are_keeps_what_they_carry() -> None:
    village = Village()

    village.hunger.collapse()

    assert village.player.items == [lamp()]
    assert village.player.left == []
    assert village.here() == HOME


def piles(*at: tuple[str, int]) -> list[Pile]:
    return [Pile(at=MapTile(map=map, x=x, y=15), items=[lamp(), WIRE]) for map, x in at]


def test_picking_up_takes_the_nearest_pile_in_reach() -> None:
    village = Village(Player(items=[], left=piles(("kapok_walk", 12), ("kapok_walk", 14))))
    village.stand(13.2, 15, "kapok_walk")

    assert village.hunger.pick_up()

    assert village.player.items == [lamp(), WIRE]
    assert village.player.left == piles(("kapok_walk", 12))


def test_picking_up_leaves_what_they_cannot_carry() -> None:
    heavy = [Pile(at=MapTile(map="kapok_walk", x=12, y=15), items=[SERVO, WIRE, BUN])]
    village = Village(Player(items=[lamp(), SERVO, SERVO], carry_limit=9, left=heavy))
    village.stand(12, 15, "kapok_walk")

    assert village.hunger.pick_up()

    assert village.player.items == [lamp(), SERVO, SERVO, WIRE, BUN]
    assert village.player.load == pytest.approx(8.7)
    assert village.player.left == [heavy[0].model_copy(update={"items": [SERVO]})]


def test_nothing_is_picked_up_with_no_room_for_any_of_it() -> None:
    heavy = [Pile(at=MapTile(map="kapok_walk", x=12, y=15), items=[SERVO])]
    village = Village(Player(items=[lamp(), SERVO, SERVO], carry_limit=8, left=heavy))
    village.stand(12, 15, "kapok_walk")

    assert not village.hunger.pick_up()
    assert village.player.left == heavy


@pytest.mark.parametrize(
    ("x", "map"), [(13.6, "kapok_walk"), (12, "high_street")], ids=["too_far", "another_map"]
)
def test_nothing_is_picked_up_out_of_reach(x: float, map: str) -> None:
    village = Village(Player(items=[], left=piles(("kapok_walk", 12))))
    village.stand(x, 15, map)

    assert not village.hunger.pick_up()
    assert village.player.items == []
    assert village.player.left == piles(("kapok_walk", 12))
