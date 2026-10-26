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
from simile.protocol import Buyer, Fitting, Treatment
from simile.schema import (
    LINES,
    PLAYER_ID,
    POWER_CELLS,
    SOLD,
    Bionic,
    Body,
    BodyPart,
    Effect,
    EffectKind,
    Item,
    ItemKind,
    Mind,
    Player,
    lamp,
)
from simile.sim import Clock, FakeWallClock, World
from simile.street.sewers import APEX_ACTUATOR
from simile.world import Movement, Point
from simile.world.map import load_maps

NOW = datetime(2026, 1, 1, 12, tzinfo=UTC)
MAPS = load_maps()
CLINIC = Point(6, 2, "clinic_floor_0")
STALL = Point(26, 15, "metro")
WIRE = PLAYER_CONFIG.salvage["metro_salvage_1"].item
RECIPES = DEFAULT_CONFIG.recipes
CELL, JACK, EYE = Bionic.POWER_CELL, Bionic.DATAJACK, Bionic.INFRARED_EYE
POWER = Fitting(bionic=CELL, name="Power cell", price=100, parts=["stomach"])
DATAJACK = Fitting(bionic=JACK, name="Datajack", price=100, parts=["vertebra"])
INFRARED = Fitting(bionic=EYE, name="Infrared eye", price=200, parts=["left_eye", "right_eye"])
POWERED = Body(stomach=CELL)
FITTED = Body(
    legs=Bionic.BIONIC_LEGS_3,
    vertebra=JACK,
    right_eye=EYE,
    left_kidney=SOLD,
    stomach=Bionic.POWER_CELL_3,
    feet=Bionic.SPRING_FEET_2,
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


def parts(*bionics: Bionic) -> list[Item]:
    """What each bionic's recipe uses up, carried."""
    return [
        Item(id=id, kind=ItemKind.PART, name=id.replace("_", " ").capitalize(), weight=0.1)
        for bionic in bionics
        for id, n in RECIPES[bionic].parts.items()
        for _ in range(n)
    ]


def knowing(*bionics: Bionic, money: float = 0, body: Body = POWERED) -> Player:
    """A player who knows each recipe and carries its parts."""
    items = [lamp(), *parts(*bionics)]
    return Player(money=money, body=body, items=items, mind=Mind(recipes=list(bionics)))


def offered(depot: Depot) -> list[Bionic]:
    return [fitting.bionic for fitting in depot.clinic.fittings()]


def test_a_whole_player_knowing_nothing_is_offered_a_kidney_sale() -> None:
    depot = Depot(Player(items=[WIRE]))

    assert depot.trade.buyer() == Buyer(
        place="clinic",
        name="The Clinic",
        prices={"copper_wire": ECONOMY.salvage["copper_wire"]},
        parts={"left_kidney": 100},
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
    assert depot.trade.buyer() == Buyer(place="clinic", name="The Clinic", prices={})


@pytest.mark.parametrize("part", ["right_kidney", "legs", "left_eye", "vertebra", "stomach"])
def test_the_doctor_buys_nothing_else_of_their_body(part: BodyPart) -> None:
    depot = Depot(Player())

    assert not depot.clinic.sell_part(part)

    assert depot.player.body == Body()
    assert depot.economy.ledger.entries == []


def test_she_fits_only_what_they_know_the_recipe_for() -> None:
    player = knowing(money=500)
    player.items = [*player.items, *parts(JACK, EYE)]
    depot = Depot(player)

    assert offered(depot) == []
    assert not depot.clinic.fit(JACK, "vertebra")
    assert not depot.clinic.fit(EYE, "left_eye")

    player.mind = Mind(recipes=[JACK])
    assert depot.clinic.fittings() == [DATAJACK]
    assert depot.clinic.fit(JACK, "vertebra")
    assert depot.player.money == 400


def test_nothing_but_the_cell_goes_in_before_the_cell() -> None:
    depot = Depot(knowing(JACK, EYE, Bionic.BIONIC_LEGS, CELL, money=1000, body=Body()))

    assert depot.clinic.fittings() == [POWER]
    for bionic, part in [(JACK, "vertebra"), (EYE, "left_eye"), (Bionic.BIONIC_LEGS, "legs")]:
        assert not depot.clinic.fit(bionic, part), bionic
    assert depot.player.body == Body()

    assert depot.clinic.fit(CELL, "stomach")
    assert offered(depot) == [JACK, Bionic.BIONIC_LEGS, EYE]
    assert depot.clinic.fit(JACK, "vertebra")


@pytest.mark.parametrize("bionic", list(RECIPES))
def test_each_fitting_takes_its_credits_its_parts_and_the_part_of_their_body(
    bionic: Bionic,
) -> None:
    recipe = RECIPES[bionic]
    body = Body() if bionic in POWER_CELLS else POWERED
    player = knowing(bionic, money=recipe.credits + 5, body=body)
    player.items = [*player.items, WIRE]
    depot = Depot(player)
    part = recipe.replaces[0]

    assert depot.clinic.fit(bionic, part)

    assert depot.player.money == 5
    assert getattr(depot.player.body, part) is bionic
    assert [item.id for item in depot.player.items] == ["lamp", WIRE.id]
    [paid] = depot.economy.ledger.entries
    assert (paid.kind, paid.payer, paid.payee, paid.place, paid.amount) == (
        Kind.PURCHASE,
        PLAYER,
        OUTSIDE,
        "clinic",
        recipe.credits,
    )
    assert bionic not in offered(depot)
    assert depot.balanced()


def test_each_fitting_is_its_recipe_in_whichever_part_is_free() -> None:
    known = list(RECIPES)
    depot = Depot(Player(money=5000, body=POWERED, mind=Mind(recipes=known)))

    for fitting in depot.clinic.fittings():
        if recipe := RECIPES.get(fitting.bionic):
            assert (fitting.name, fitting.price) == (recipe.name, recipe.credits)
            assert fitting.parts == recipe.replaces


@pytest.mark.parametrize("short", ["a part", "a credit"])
def test_short_of_a_part_or_the_credits_nothing_is_fitted(short: str) -> None:
    credits = RECIPES[JACK].credits
    player = knowing(JACK, money=credits if short == "a part" else credits - 0.5)
    if short == "a part":
        player.items = player.items[:-1]
    before = player.model_copy(deep=True)
    depot = Depot(player)

    assert DATAJACK in depot.clinic.fittings()
    assert not depot.clinic.fit(JACK, "vertebra")

    assert depot.player == before
    assert depot.economy.ledger.entries == []


def test_a_higher_grade_goes_in_place_of_the_lower_which_she_takes_back() -> None:
    legs, better = Bionic.BIONIC_LEGS, Bionic.BIONIC_LEGS_2
    body = Body(stomach=CELL, legs=legs)
    depot = Depot(knowing(legs, better, money=RECIPES[better].credits, body=body))

    assert legs not in offered(depot)
    assert depot.clinic.fit(better, "legs")

    assert depot.player.body == Body(stomach=CELL, legs=better)
    assert depot.player.money == 0
    assert legs not in offered(depot) and better not in offered(depot)


def test_she_fits_nothing_past_what_their_cell_runs_until_a_bigger_cell_is_in() -> None:
    three = Body(stomach=CELL, vertebra=JACK, legs=Bionic.BIONIC_LEGS, feet=Bionic.SPRING_FEET)
    bigger = Bionic.POWER_CELL_2
    depot = Depot(knowing(EYE, bigger, money=1000, body=three))

    assert EYE not in offered(depot)
    assert not depot.clinic.fit(EYE, "left_eye")
    assert depot.clinic.fit(bigger, "stomach")
    assert depot.clinic.fit(EYE, "left_eye")
    assert depot.player.body == three.model_copy(update={"stomach": bigger, "left_eye": EYE})


@pytest.mark.parametrize(
    ("bionic", "part"),
    [
        (Bionic.BIONIC_LEGS, "vertebra"),
        (JACK, "left_eye"),
        (EYE, "legs"),
        (EYE, "left_kidney"),
        (CELL, "vertebra"),
    ],
)
def test_a_bionic_goes_only_in_place_of_its_part(bionic: Bionic, part: BodyPart) -> None:
    depot = Depot(knowing(JACK, EYE, CELL, money=500, body=Body()))

    assert not depot.clinic.fit(bionic, part)

    assert depot.player.body == Body()
    assert depot.player.money == 500


def test_there_is_one_infrared_eye_for_either_eye() -> None:
    player = knowing(EYE, money=500)
    player.items = [*player.items, *parts(EYE)]
    depot = Depot(player)

    assert INFRARED in depot.clinic.fittings()
    assert depot.clinic.fit(EYE, "right_eye")

    assert EYE not in offered(depot)
    assert not depot.clinic.fit(EYE, "left_eye")
    assert depot.player.body == Body(stomach=CELL, right_eye=EYE)
    assert depot.player.money == 300


def test_with_everything_fitted_the_doctor_only_buys_salvage() -> None:
    depot = Depot(Player(body=FITTED, items=[WIRE], mind=Mind(recipes=[CELL], sold=[CELL])))

    assert depot.clinic.fittings() == []
    assert depot.clinic.parts() == {}
    assert depot.trade.buyer() == Buyer(
        place="clinic", name="The Clinic", prices={"copper_wire": 6}
    )


def test_the_doctor_fits_only_what_they_stock() -> None:
    stock = dict.fromkeys(Bionic, 1) | {JACK: 0}
    config = DEFAULT_CONFIG.model_copy(update={"stock": stock})
    depot = Depot(knowing(JACK, EYE, money=500), config)

    assert depot.clinic.fittings() == [INFRARED]
    assert not depot.clinic.fit(JACK, "vertebra")
    assert depot.player.money == 500


def test_nothing_is_bought_sold_or_fitted_outside_the_clinic() -> None:
    depot = Depot(knowing(JACK, money=500))
    depot.stand(STALL)

    assert not depot.clinic.sell_part("left_kidney")
    assert not depot.clinic.fit(Bionic.BIONIC_LEGS, "legs")
    assert not depot.clinic.fit(JACK, "vertebra")
    assert not depot.clinic.sell_recipe(JACK)
    assert depot.player.body == POWERED
    assert depot.player.money == 500
    assert depot.trade.buyer() == Buyer(
        place="scrap_stall", name="The scrap trader's stall", prices={"usb_c_connector": 12}
    )


def test_she_buys_each_recipe_they_know_once_and_they_still_know_it() -> None:
    depot = Depot(knowing(CELL, JACK, money=3))
    worth = DEFAULT_CONFIG.procedures[JACK].buys

    assert depot.trade.buyer().recipes == {JACK: worth}
    assert not depot.clinic.sell_recipe(CELL), "her own recipe, which she teaches"
    assert not depot.clinic.sell_recipe(EYE), "a recipe they don't know"
    assert depot.clinic.sell_recipe(JACK)

    assert depot.player.money == 3 + worth
    assert depot.player.mind == Mind(recipes=[CELL, JACK], sold=[JACK])
    assert depot.clinic.recipes() == {}
    assert not depot.clinic.sell_recipe(JACK)
    assert depot.player.money == 3 + worth
    [sale] = depot.economy.ledger.entries
    assert (sale.kind, sale.payer, sale.payee, sale.amount) == (
        Kind.SALVAGE,
        OUTSIDE,
        PLAYER,
        worth,
    )
    assert depot.balanced()


def test_she_still_builds_from_a_recipe_they_sold_her() -> None:
    depot = Depot(knowing(JACK, money=RECIPES[JACK].credits))
    assert depot.clinic.sell_recipe(JACK)

    assert depot.clinic.fit(JACK, "vertebra")


def test_she_buys_every_recipe_but_the_cell_for_less_than_it_costs_to_build() -> None:
    for bionic, procedure in DEFAULT_CONFIG.procedures.items():
        if bionic in POWER_CELLS[:1]:
            assert procedure.buys is None
        else:
            assert procedure.buys is not None and 0 < procedure.buys < procedure.recipe.credits


def test_the_datajacks_recipe_is_the_plans() -> None:
    assert RECIPES[JACK].parts == {"copper_wire": 3, "usb_c_connector": 1}
    assert RECIPES[JACK].credits == 100
    assert RECIPES[Bionic.BIONIC_LEGS_3].parts[APEX_ACTUATOR.id] == 1


def test_everything_but_a_cell_waits_for_the_cell() -> None:
    for bionic, recipe in RECIPES.items():
        assert recipe.after == ([] if bionic in POWER_CELLS else [CELL]), bionic


def test_the_kidney_pays_for_the_cell() -> None:
    assert RECIPES[CELL].credits <= DEFAULT_CONFIG.kidney


def test_each_grade_of_a_line_costs_more_than_the_one_before() -> None:
    for line in LINES:
        credits = [RECIPES[grade].credits for grade in line]
        assert credits == sorted(credits) and len(set(credits)) == len(credits), line


BITTEN = Effect(kind=EffectKind.RAT_BITE, strength=0.4, fades=0.25, since=NOW)
INFECTED = Effect(kind=EffectKind.INFECTION, strength=0.6, fades=None, since=NOW)
DOSE = Effect(kind=EffectKind.RADIATION, strength=0.5, fades=0.05, since=NOW)


def test_she_patches_up_the_hurt_for_less_the_less_hurt_they_are() -> None:
    assert Depot(Player()).clinic.treatments() == []
    for health, price in [(0.0, 30), (0.5, 15), (0.99, 1)]:
        depot = Depot(Player(health=health))

        assert depot.clinic.treatments() == [Treatment(effect=None, name="Patch up", price=price)]


def test_she_treats_a_bite_and_an_infection_but_not_a_dose() -> None:
    depot = Depot(Player(effects=[BITTEN, DOSE, INFECTED]))

    assert depot.trade.buyer().treatments == [
        Treatment(effect=EffectKind.RAT_BITE, name="Clean the bite", price=5),
        Treatment(effect=EffectKind.INFECTION, name="Treat the infection", price=25),
    ]


def test_patching_up_brings_them_to_full_health_through_the_ledger() -> None:
    depot = Depot(Player(money=20, health=0.5, effects=[INFECTED]))

    assert depot.clinic.treat(None)

    assert depot.player.health == 1
    assert depot.player.money == 5
    assert depot.player.effects == [INFECTED]
    [entry] = depot.economy.ledger.entries
    assert (entry.kind, entry.payer, entry.payee, entry.place, entry.amount) == (
        Kind.PURCHASE,
        PLAYER,
        OUTSIDE,
        "clinic",
        15,
    )
    assert depot.balanced()


def test_treating_an_infection_ends_it_and_nothing_else() -> None:
    depot = Depot(Player(money=30, health=0.5, effects=[DOSE, INFECTED]))

    assert depot.clinic.treat(EffectKind.INFECTION)

    assert depot.player.effects == [DOSE]
    assert depot.player.health == 0.5
    assert depot.player.money == 5


def test_she_gives_no_treatment_they_cant_pay_for_dont_need_or_outside() -> None:
    depot = Depot(Player(money=10, health=0.5, effects=[INFECTED, DOSE]))

    assert not depot.clinic.treat(EffectKind.INFECTION)
    assert not depot.clinic.treat(EffectKind.RADIATION)
    assert not depot.clinic.treat(EffectKind.RAT_BITE)
    depot.stand(STALL)
    assert not depot.clinic.treat(None)

    assert depot.player.money == 10
    assert depot.economy.ledger.entries == []
