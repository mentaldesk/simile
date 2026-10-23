import json
from datetime import UTC, datetime

import pytest

from simile.behaviour import Behaviour
from simile.clinic.clinic import Clinic
from simile.clinic.config import DEFAULT_CONFIG, ClinicConfig
from simile.economy import DEFAULT_CONFIG as ECONOMY
from simile.economy import OUTSIDE, PLAYER, Kind
from simile.economy.economy import Economy
from simile.memory import MemoryStore
from simile.npc import load_npcs
from simile.player.config import DEFAULT_CONFIG as PLAYER_CONFIG
from simile.player.trade import Trade
from simile.protocol import Buyer, Fitting
from simile.schema import LEGS as GRADES
from simile.schema import PLAYER_ID, SOLD, Bionic, Body, BodyPart, Player
from simile.sim import Clock, FakeWallClock, World
from simile.street.jump import GRADES as JUMPS
from simile.street.jump import meets
from simile.street.sewers import APEX_ACTUATOR
from simile.world import Movement, Point
from simile.world.map import STREET_DIR, load_maps

NOW = datetime(2026, 1, 1, 12, tzinfo=UTC)
MAPS = load_maps()
CLINIC = Point(6, 2, "clinic_floor_0")
STALL = Point(26, 15, "metro")
WIRE = PLAYER_CONFIG.salvage["metro_salvage_1"].item
LEGS = Fitting(bionic=Bionic.HYDRAULIC_LEGS, name="Hydraulic legs", price=80, parts=["legs"])
SPRINT = Fitting(bionic=Bionic.SPRINT_LEGS, name="Sprint legs", price=80, parts=["legs"])
DATAJACK = Fitting(bionic=Bionic.DATAJACK, name="Datajack", price=150, parts=["vertebra"])
EYE = Fitting(
    bionic=Bionic.INFRARED_EYE, name="Infrared eye", price=200, parts=["left_eye", "right_eye"]
)
FITTED = Body(
    legs=Bionic.PREMIUM_LEGS,
    vertebra=Bionic.DATAJACK,
    right_eye=Bionic.INFRARED_EYE,
    left_kidney=SOLD,
)


class Depot:
    def __init__(self, player: Player, config: ClinicConfig = DEFAULT_CONFIG) -> None:
        world = World(Clock(NOW), FakeWallClock())
        self.movement = Movement(MAPS, world.bus)
        behaviour = Behaviour(
            world.clock, world.bus, self.movement, load_npcs()[:2], MemoryStore(":memory:"), seed=0
        )
        self.player = player
        self.start = player.money
        self.economy = Economy(world.clock, behaviour, player=player)
        self.clinic = Clinic(player, self.movement, self.economy, world.clock, config)
        keepers = {config.place: self.clinic.keep}
        self.trade = Trade(player, self.movement, self.economy, world.clock, keepers)
        self.stand(CLINIC)

    def stand(self, at: Point) -> None:
        self.movement.track(PLAYER_ID, at)

    def balanced(self) -> bool:
        ledger = self.economy.ledger
        gained = ledger.net(PLAYER) == pytest.approx(self.player.money - self.start)
        return gained and ledger.gap(self.economy.money) == pytest.approx(0)


def test_a_whole_player_is_offered_a_kidney_sale_and_every_bionic() -> None:
    depot = Depot(Player(items=[WIRE]))

    assert depot.trade.buyer() == Buyer(
        place="clinic",
        name="The Clinic",
        prices={"copper_wire": ECONOMY.salvage["copper_wire"]},
        parts={"left_kidney": 100},
        fittings=[LEGS, SPRINT, DATAJACK, EYE],
    )


def test_selling_a_kidney_pays_the_doctors_price_through_the_ledger() -> None:
    depot = Depot(Player(money=3))

    assert depot.clinic.sell_part("left_kidney")

    assert depot.player.money == 3 + DEFAULT_CONFIG.kidney
    assert depot.player.body == Body(left_kidney=SOLD)
    [sale] = depot.economy.ledger.entries
    assert (sale.kind, sale.payer, sale.payee, sale.place) == (
        Kind.SALVAGE,
        OUTSIDE,
        PLAYER,
        "clinic",
    )
    assert sale.amount == 100
    assert depot.balanced()


@pytest.mark.parametrize("part", ["left_kidney", "right_kidney"])
def test_the_doctor_buys_one_kidney_and_never_the_last(part: BodyPart) -> None:
    depot = Depot(Player())
    assert depot.clinic.sell_part("left_kidney")

    assert depot.clinic.parts() == {}
    assert not depot.clinic.sell_part(part)
    assert depot.player.money == 100
    assert depot.trade.buyer() == Buyer(
        place="clinic", name="The Clinic", prices={}, fittings=[LEGS, SPRINT, DATAJACK, EYE]
    )


@pytest.mark.parametrize("part", ["right_kidney", "legs", "left_eye", "vertebra"])
def test_the_doctor_buys_nothing_else_of_their_body(part: BodyPart) -> None:
    depot = Depot(Player())

    assert not depot.clinic.sell_part(part)

    assert depot.player.body == Body()
    assert depot.economy.ledger.entries == []


@pytest.mark.parametrize(
    ("bionic", "part", "price"),
    [
        (Bionic.HYDRAULIC_LEGS, "legs", 80),
        (Bionic.DATAJACK, "vertebra", 150),
        (Bionic.INFRARED_EYE, "left_eye", 200),
        (Bionic.INFRARED_EYE, "right_eye", 200),
    ],
)
def test_each_fitting_takes_the_money_and_the_part(
    bionic: Bionic, part: BodyPart, price: float
) -> None:
    depot = Depot(Player(money=price + 5))

    assert depot.clinic.fit(bionic, part)

    assert depot.player.money == 5
    assert getattr(depot.player.body, part) is bionic
    assert depot.player.body.bionics == [bionic]
    assert depot.player.humanity == 1 - bionic.humanity_cost
    [paid] = depot.economy.ledger.entries
    assert (paid.kind, paid.payer, paid.payee, paid.place, paid.amount) == (
        Kind.PURCHASE,
        PLAYER,
        OUTSIDE,
        "clinic",
        price,
    )
    assert bionic not in [fitting.bionic for fitting in depot.clinic.fittings()]
    assert depot.balanced()


@pytest.mark.parametrize(
    ("bionic", "part"),
    [
        (Bionic.HYDRAULIC_LEGS, "legs"),
        (Bionic.DATAJACK, "vertebra"),
        (Bionic.INFRARED_EYE, "left_eye"),
    ],
)
def test_you_cant_buy_what_you_cant_afford(bionic: Bionic, part: BodyPart) -> None:
    price = DEFAULT_CONFIG.offers[bionic].price
    depot = Depot(Player(money=price - 0.5))

    assert not depot.clinic.fit(bionic, part)

    assert depot.player.money == price - 0.5
    assert depot.player.body == Body()
    assert depot.economy.ledger.entries == []
    assert bionic in [fitting.bionic for fitting in depot.clinic.fittings()]


@pytest.mark.parametrize(
    ("bionic", "part"),
    [
        (Bionic.HYDRAULIC_LEGS, "vertebra"),
        (Bionic.DATAJACK, "left_eye"),
        (Bionic.INFRARED_EYE, "legs"),
        (Bionic.INFRARED_EYE, "left_kidney"),
    ],
)
def test_a_bionic_goes_only_in_place_of_its_part(bionic: Bionic, part: BodyPart) -> None:
    depot = Depot(Player(money=500))

    assert not depot.clinic.fit(bionic, part)

    assert depot.player.body == Body()
    assert depot.player.money == 500


def test_there_is_one_infrared_eye_for_either_eye() -> None:
    depot = Depot(Player(money=500))

    assert depot.clinic.fit(Bionic.INFRARED_EYE, "right_eye")

    assert EYE not in depot.clinic.fittings()
    assert not depot.clinic.fit(Bionic.INFRARED_EYE, "left_eye")
    assert depot.player.body == Body(right_eye=Bionic.INFRARED_EYE)
    assert depot.player.money == 300


def test_with_everything_fitted_the_doctor_only_buys_salvage() -> None:
    depot = Depot(Player(body=FITTED, items=[WIRE]))

    assert depot.clinic.fittings() == []
    assert depot.clinic.parts() == {}
    assert depot.trade.buyer() == Buyer(
        place="clinic", name="The Clinic", prices={"copper_wire": 6}
    )


def test_the_doctor_fits_only_what_they_stock() -> None:
    stock = dict.fromkeys(Bionic, 1) | {Bionic.DATAJACK: 0}
    depot = Depot(Player(money=500), DEFAULT_CONFIG.model_copy(update={"stock": stock}))

    assert depot.clinic.fittings() == [LEGS, SPRINT, EYE]
    assert not depot.clinic.fit(Bionic.DATAJACK, "vertebra")
    assert depot.player.money == 500


def test_nothing_is_bought_or_fitted_outside_the_clinic() -> None:
    depot = Depot(Player(money=500))
    depot.stand(STALL)

    assert not depot.clinic.sell_part("left_kidney")
    assert not depot.clinic.fit(Bionic.HYDRAULIC_LEGS, "legs")
    assert depot.player.body == Body()
    assert depot.player.money == 500
    assert depot.trade.buyer() == Buyer(
        place="scrap_stall", name="The scrap trader's stall", prices={}
    )


def test_the_prices_carry_s15s_loop() -> None:
    """The kidney buys the legs; the secrets they reach and two days of salvage the datajack."""
    reached = [p for p in metro_pickups() if meets(JUMPS[Bionic.HYDRAULIC_LEGS], p["needs"])]
    prices = DEFAULT_CONFIG.offers
    salvage = sum(
        ECONOMY.salvage[PLAYER_CONFIG.salvage[p["name"]].item.id]
        for p in reached
        if p["type"] == "salvage"
    )
    secrets = sum(p.get("money", 0) for p in reached if p["type"] == "secret")
    meals = 2 * 2 * ECONOMY.shops["coffee_shop"].meal
    legs, datajack, eye = (prices[b].price for b in (LEGS.bionic, DATAJACK.bionic, EYE.bionic))

    assert salvage == 50 - ECONOMY.salvage["brass_valve"], "the valve is up with the spring legs"
    assert secrets == 25 + 40 + 60, "the stairwell's, the catwalk's and the high ledge's"
    left = DEFAULT_CONFIG.kidney - legs
    assert left >= 0
    left += secrets + 2 * salvage - meals - datajack
    assert left >= 0
    days = (eye - left) / (salvage - meals / 2)
    assert 4 <= days <= 6


def test_each_grade_of_legs_costs_steeply_more_than_the_one_before() -> None:
    prices = {bionic: offer.price for bionic, offer in DEFAULT_CONFIG.offers.items()}
    eye = prices[Bionic.INFRARED_EYE]

    for legs in GRADES:
        for before in DEFAULT_CONFIG.offers[legs].after:
            assert prices[legs] >= 2.5 * prices[before], (legs, before)
    assert prices[Bionic.SPRINT_LEGS] == prices[Bionic.HYDRAULIC_LEGS]
    assert prices[Bionic.SPRING_LEGS] == prices[Bionic.BLADE_LEGS] > eye


def metro_pickups() -> list[dict]:
    """Each pickup on the metro: its name, type and properties, with `needs` "jump" for a walk."""
    data = json.loads((STREET_DIR / "metro.tmj").read_text())
    [layer] = [layer for layer in data["layers"] if layer["name"] == "pickups"]
    return [
        {"name": o["name"], "type": o["type"], "needs": "jump"}
        | {p["name"]: p["value"] for p in o.get("properties", [])}
        for o in layer["objects"]
    ]


def offered(depot: Depot) -> list[Bionic]:
    return [fitting.bionic for fitting in depot.clinic.fittings()]


@pytest.mark.parametrize(
    ("legs", "next_grades"),
    [
        ("present", [Bionic.HYDRAULIC_LEGS, Bionic.SPRINT_LEGS]),
        (Bionic.HYDRAULIC_LEGS, [Bionic.SPRING_LEGS]),
        (Bionic.SPRINT_LEGS, [Bionic.BLADE_LEGS]),
        (Bionic.SPRING_LEGS, []),
        (Bionic.BLADE_LEGS, []),
        (Bionic.PREMIUM_LEGS, []),
    ],
)
def test_the_clinic_stocks_the_next_grade_only_after_the_one_before(
    legs: str, next_grades: list[Bionic]
) -> None:
    depot = Depot(Player(money=5000, body=Body(legs=legs)))

    assert [bionic for bionic in offered(depot) if bionic in GRADES] == next_grades
    for grade in set(GRADES) - set(next_grades):
        assert not depot.clinic.fit(grade, "legs"), grade
    assert depot.player.body.legs == legs and depot.player.money == 5000


def test_an_upgrade_takes_the_legs_before_it_back_for_its_price() -> None:
    depot = Depot(Player(money=300, body=Body(legs=Bionic.HYDRAULIC_LEGS)))
    [spring] = [f for f in depot.clinic.fittings() if f.bionic is Bionic.SPRING_LEGS]

    assert spring.parts == ["legs"] and spring.price == 240
    assert depot.clinic.fit(Bionic.SPRING_LEGS, "legs")

    assert depot.player.body == Body(legs=Bionic.SPRING_LEGS)
    assert depot.player.money == 60
    assert depot.player.humanity == 1 - Bionic.HYDRAULIC_LEGS.humanity_cost
    assert Bionic.SPRING_LEGS not in offered(depot)
    assert depot.balanced()


@pytest.mark.parametrize("legs", [Bionic.SPRING_LEGS, Bionic.BLADE_LEGS])
def test_premium_legs_need_the_apex_actuator_which_the_fitting_uses_up(legs: Bionic) -> None:
    depot = Depot(Player(money=700, body=Body(legs=legs)))

    assert Bionic.PREMIUM_LEGS not in offered(depot)
    assert not depot.clinic.fit(Bionic.PREMIUM_LEGS, "legs")

    depot.player.items = [*depot.player.items, APEX_ACTUATOR, WIRE]
    assert Bionic.PREMIUM_LEGS in offered(depot)
    assert depot.clinic.fit(Bionic.PREMIUM_LEGS, "legs")

    assert depot.player.body.legs is Bionic.PREMIUM_LEGS
    assert depot.player.money == 100
    assert [item.id for item in depot.player.items] == ["lamp", WIRE.id]
    assert DEFAULT_CONFIG.offers[Bionic.PREMIUM_LEGS].needs == APEX_ACTUATOR
