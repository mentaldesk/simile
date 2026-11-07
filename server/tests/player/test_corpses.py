import json
import os
import random
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from simile.behaviour import Behaviour
from simile.clinic.clinic import Clinic
from simile.clinic.config import DEFAULT_CONFIG as CLINIC_CONFIG
from simile.economy import PILES, PLAYER, Kind
from simile.economy.economy import Economy
from simile.memory import MemoryStore
from simile.npc import load_npcs
from simile.persistence import WorldStore, capture
from simile.player.corpses import BIONIC_WEIGHTS, Death, Salvage, next_corpse
from simile.player.health import Health
from simile.player.hunger import Hunger
from simile.player.pickups import Pickups
from simile.protocol import TakeMessage, Vital
from simile.schema import (
    PLAYER_ID,
    SOLD,
    Bionic,
    Body,
    Corpse,
    Effect,
    EffectKind,
    Item,
    ItemKind,
    MapTile,
    Mind,
    Pile,
    Player,
    Sale,
    Stash,
    lamp,
)
from simile.sim import Clock, FakeWallClock, World
from simile.world import Movement, Point
from simile.world.map import load_maps
from simile.world.paths import Spot

MAPS = load_maps()
NOW = datetime(2026, 1, 1, 12, tzinfo=UTC)
BED = Spot("maker_space_floor_2", 5, 2)
WOKEN = MapTile(map=BED.map, x=BED.x, y=BED.y)
CLINIC = Point(6, 2, "clinic_floor_0")
WIRE = Item(id="copper_wire", kind=ItemKind.SALVAGE, name="Copper wire", weight=1.5)
BUN = Item(id="pork_bun", kind=ItemKind.FOOD, name="Pork bun", weight=0.2)
FITTED = Body(
    legs=Bionic.BIONIC_LEGS_2,
    vertebra=Bionic.DATAJACK,
    left_kidney=SOLD,
    stomach=Bionic.POWER_CELL,
)
OLD_SAVE = """{
  "money": 4.0,
  "items": [{"id": "lamp", "kind": "lamp", "name": "Lamp", "weight": 1.0,
             "charge": 0.5, "on": false}],
  "body": {"legs": "present", "vertebra": "present", "left_eye": "present", "right_eye": "present",
           "left_kidney": "sold", "right_kidney": "present"},
  "hunger": 0.75,
  "left": [
    {"at": {"map": "kapok_walk", "x": 12, "y": 15},
     "items": [{"id": "pork_bun", "kind": "food", "name": "Pork bun", "weight": 0.2}],
     "money": 20.0},
    {"at": {"map": "kapok_walk", "x": 30, "y": 15}, "items": [], "money": 8.0}
  ]
}"""


class Fall:
    def __init__(self, player: Player | None = None) -> None:
        self.world = World(Clock(NOW), FakeWallClock())
        self.movement = Movement(MAPS, self.world.bus)
        self.behaviour = behaviour = Behaviour(
            self.world.clock,
            self.world.bus,
            self.movement,
            load_npcs()[:2],
            MemoryStore(":memory:"),
            seed=0,
        )
        self.player = player or Player()
        self.economy = Economy(self.world.clock, behaviour, player=self.player)
        self.woke: list[tuple[MapTile, Vital]] = []
        self.death = self.dying(self.player)

    def dying(self, player: Player) -> Death:
        return Death(
            player,
            self.movement,
            self.world.clock,
            economy=self.economy,
            bed=lambda: BED,
            woke=lambda home, cause: self.woke.append((home, cause)),
        )

    def stand(self, x: float, y: float, map: str) -> None:
        self.movement.track(PLAYER_ID, Point(x, y, map))

    def here(self) -> Point:
        return self.movement.position(PLAYER_ID)


@pytest.mark.parametrize("cause", list(Vital))
def test_a_death_leaves_a_corpse_with_everything_but_the_lamp_where_they_fell(cause: Vital) -> None:
    lit = lamp().model_copy(update={"charge": 0.3, "on": True})
    fall = Fall(Player(money=31.5, items=[WIRE, lit, BUN], body=FITTED))
    fall.stand(12.3, 15, "kapok_walk")

    fall.death.die(cause)

    assert fall.player.corpses == [
        Corpse(
            id="corpse_1",
            owner=PLAYER_ID,
            at=MapTile(map="kapok_walk", x=12, y=15),
            money=31.5,
            items=[WIRE, BUN],
            bionics=[Bionic.BIONIC_LEGS_2, Bionic.DATAJACK, Bionic.POWER_CELL],
        )
    ]
    assert fall.player.items == [lit]
    assert fall.player.money == 0
    assert fall.player.left == []
    assert fall.here() == Point(BED.x, BED.y, BED.map)
    assert fall.woke == [(WOKEN, cause)]


def test_they_wake_whole_and_well_in_a_new_body() -> None:
    bite = Effect(kind=EffectKind.RAT_BITE, strength=0.4, fades=0.25, since=NOW)
    sick = Effect(kind=EffectKind.INFECTION, strength=0.2, fades=None, since=NOW)
    flat = Player(body=FITTED, effects=[bite, sick], power=0.0, health=0.5)
    fall = Fall(flat)
    fall.stand(12, 15, "kapok_walk")

    fall.death.die(Vital.POWER)

    assert fall.player.body == Body()
    assert fall.player.effects == []
    assert fall.player.power == 1
    assert fall.player.health == fall.death.health.waking
    assert fall.player.humanity == 1


@pytest.mark.parametrize(
    ("before", "after"),
    [(1.0, 0.75), (0.9, 0.75), (0.2, 0.2), (0.0, 0.0)],
    ids=["starving", "nearly", "fed", "on_a_cell"],
)
@pytest.mark.parametrize("cause", list(Vital))
def test_they_never_wake_starving(cause: Vital, before: float, after: float) -> None:
    fall = Fall(Player(hunger=before))
    fall.stand(12, 15, "kapok_walk")

    fall.death.die(cause)

    assert fall.player.hunger == after


def test_what_is_not_their_body_stays_theirs() -> None:
    stored = Stash(items=[WIRE])
    pile = Pile(at=MapTile(map="metro", x=3, y=15), items=[BUN])
    sale = Sale(item=WIRE, place="scrap_stall", price=6)
    mind = Mind(recipes=[Bionic.DATAJACK, Bionic.POWER_CELL], sold=[Bionic.POWER_CELL])
    fall = Fall(
        Player(
            stash=stored,
            left=[pile],
            sales=[sale],
            mind=mind,
            searched=["maker_space_bench"],
            repaired=["printer_3d"],
            taken={"metro_secret_cache": NOW},
            carry_limit=20,
        )
    )
    fall.stand(12, 15, "kapok_walk")

    fall.death.die(Vital.HEALTH)

    assert fall.player.stash == stored
    assert fall.player.left == [pile]
    assert fall.player.sales == [sale]
    assert fall.player.mind == mind
    assert fall.player.searched == ["maker_space_bench"]
    assert fall.player.repaired == ["printer_3d"]
    assert fall.player.taken == {"metro_secret_cache": NOW}
    assert fall.player.carry_limit == 20


def test_the_money_on_a_corpse_goes_through_the_ledger() -> None:
    fall = Fall(Player(money=31.5))
    fall.stand(12, 15, "kapok_walk")

    fall.death.die(Vital.HUNGER)

    entries = fall.economy.ledger.entries
    assert [(e.kind, e.amount, e.payer, e.payee) for e in entries] == [
        (Kind.DROPPED, 31.5, PLAYER, PILES)
    ]
    assert fall.economy.ledger.gap(fall.economy.money) == 0


@pytest.mark.parametrize(
    ("x", "y", "ground"),
    [(17.2, 5.6, (17, 8)), (22.4, 5, (22, 15)), (3, 13.5, (3, 15))],
    ids=["over_a_roof", "over_a_gap", "on_a_ladder"],
)
def test_a_corpse_falls_to_the_ground_below(x: float, y: float, ground: tuple[int, int]) -> None:
    fall = Fall(Player(money=1.0))
    fall.stand(x, y, "rooftops")

    fall.death.die(Vital.HEALTH)

    assert fall.player.corpses[0].at == MapTile(map="rooftops", x=ground[0], y=ground[1])


def test_a_second_death_leaves_a_second_corpse_and_both_stay() -> None:
    fall = Fall(Player(money=10, items=[lamp(), WIRE], body=FITTED))
    fall.stand(70, 15, "high_street")
    fall.death.die(Vital.HUNGER)
    fall.player.items = [*fall.player.items, BUN]
    fall.stand(70, 15, "high_street")
    before = fall.player.corpses

    fall.death.die(Vital.HEALTH)

    assert fall.player.corpses is not before, "append skips the duplicate-id check"
    first, second = fall.player.corpses
    assert first.id != second.id
    assert first.at == second.at == MapTile(map="high_street", x=70, y=15)
    assert (first.money, first.items, first.bionics) == (10, [WIRE], FITTED.bionics)
    assert (second.money, second.items, second.bionics) == (0, [BUN], [])


def test_corpses_survive_a_save_and_a_reload_and_the_next_gets_a_new_id() -> None:
    fall = Fall(Player(money=10, items=[lamp(), WIRE], body=FITTED))
    fall.stand(12, 15, "kapok_walk")
    fall.death.die(Vital.HUNGER)

    loaded = Player.model_validate_json(fall.player.model_dump_json())
    assert loaded == fall.player
    loaded.items = [lamp(), WIRE]
    fall.dying(loaded).die(Vital.POWER)

    reloaded = Player.model_validate_json(loaded.model_dump_json())
    assert [corpse.id for corpse in reloaded.corpses] == ["corpse_1", "corpse_2"]
    assert reloaded.corpses[0] == fall.player.corpses[0]


def test_corpses_survive_the_world_being_saved_and_loaded(tmp_path: Path) -> None:
    fall = Fall(Player(money=10, items=[lamp(), WIRE], body=FITTED))
    fall.stand(12, 15, "kapok_walk")
    fall.death.die(Vital.HUNGER)
    fall.stand(30, 15, "kapok_walk")
    fall.player.items = [lamp(), WIRE]
    fall.death.die(Vital.HEALTH)
    path = tmp_path / "simile.db"

    with MemoryStore(path) as memory, WorldStore(memory) as store:
        store.save(capture(fall.behaviour, player=fall.player))
    with MemoryStore(path) as memory, WorldStore(memory) as store:
        loaded = store.load()

    assert loaded is not None
    assert loaded.player == fall.player
    assert [corpse.id for corpse in loaded.player.corpses] == ["corpse_1", "corpse_2"]


def test_a_saved_worlds_emptied_corpses_clear_on_load(tmp_path: Path) -> None:
    at = MapTile(map="sewers", x=3, y=15)
    empty = Corpse(id="corpse_1", owner=PLAYER_ID, at=at, money=0, items=[], bionics=[])
    fall = Fall(Player(corpses=[empty]))
    path = tmp_path / "simile.db"

    with MemoryStore(path) as memory, WorldStore(memory) as store:
        store.save(capture(fall.behaviour, player=fall.player))
    with MemoryStore(path) as memory, WorldStore(memory) as store:
        loaded = store.load()

    assert loaded is not None
    assert loaded.player.corpses == []
    assert (loaded.player.bodies, loaded.player.lift_open) == (1, True)


def test_an_id_that_cleared_on_load_is_not_used_again() -> None:
    at = MapTile(map="kapok_walk", x=3, y=15)
    empty = Corpse(id="corpse_1", owner=PLAYER_ID, at=at, money=0, items=[], bionics=[])
    loaded = Player.model_validate_json(Player(corpses=[empty]).model_dump_json())
    assert loaded.corpses == []
    loaded.items = [lamp(), WIRE]
    fall = Fall(loaded)
    fall.stand(12, 15, "kapok_walk")

    fall.death.die(Vital.HEALTH)

    assert [corpse.id for corpse in loaded.corpses] == ["corpse_2"]
    assert loaded.bodies == 2


def test_the_id_skips_any_already_taken() -> None:
    at = MapTile(map="metro", x=3, y=15)
    corpse = Corpse(id="corpse_2", owner=PLAYER_ID, at=at, money=0, items=[], bionics=[])

    assert next_corpse(Player(corpses=[corpse])) == "corpse_3"
    assert next_corpse(Player(corpses=[corpse], bodies=1)) == "corpse_3"
    assert next_corpse(Player(corpses=[corpse], bodies=5)) == "corpse_6"
    with pytest.raises(ValidationError, match="own id"):
        Player(corpses=[corpse, corpse])


def test_dying_before_the_server_knows_where_they_are_leaves_the_corpse_where_they_wake() -> None:
    fall = Fall(Player(money=5, items=[lamp(), WIRE], body=FITTED))

    fall.death.die(Vital.HEALTH)

    corpse = fall.player.corpses[0]
    assert corpse.at.map == BED.map and corpse.at.x == BED.x
    assert (corpse.money, corpse.items, corpse.bionics) == (5, [WIRE], FITTED.bionics)
    assert fall.player.body == Body()


def test_the_new_kidney_sells_again_and_the_recipe_they_sold_does_not() -> None:
    fall = Fall(Player(mind=Mind(recipes=[Bionic.DATAJACK], sold=[Bionic.DATAJACK])))
    clinic = Clinic(fall.player, fall.movement, fall.economy, fall.world.clock)
    fall.stand(CLINIC.x, CLINIC.y, CLINIC.map)
    assert clinic.sell_part("left_kidney")
    assert clinic.parts() == {}
    assert not clinic.sell_part("left_kidney")
    assert fall.player.money == clinic.config.kidney

    fall.death.die(Vital.HUNGER)
    assert fall.player.corpses[0].money == clinic.config.kidney
    assert fall.player.body.left_kidney != SOLD
    fall.stand(CLINIC.x, CLINIC.y, CLINIC.map)

    assert clinic.parts() == {"left_kidney": clinic.config.kidney}
    assert clinic.sell_part("left_kidney")
    assert fall.player.money == clinic.config.kidney
    assert fall.player.body.left_kidney == SOLD
    assert clinic.recipes() == {}


def test_a_save_with_piles_from_before_corpses_loads_and_gives_them_up() -> None:
    player = Player.model_validate_json(OLD_SAVE)
    assert player.corpses == []
    assert [pile.money for pile in player.left] == [20, 8]
    fall = Fall(player)
    pickups = Pickups(player, fall.movement, fall.economy, fall.world.clock)

    fall.stand(30, 15, "kapok_walk")
    assert pickups.pick_up()
    assert player.money == 12
    assert [pile.money for pile in player.left] == [20]
    fall.stand(12, 15, "kapok_walk")
    assert pickups.pick_up()
    assert player.money == 32
    assert [item.id for item in player.items] == ["lamp", "pork_bun"]
    assert player.left == []
    assert player == Player.model_validate_json(player.model_dump_json())


def test_dying_keeps_what_is_in_left_beside_the_new_corpse() -> None:
    player = Player.model_validate_json(OLD_SAVE)
    fall = Fall(player)
    fall.stand(70, 15, "high_street")

    fall.death.die(Vital.HEALTH)

    assert [pile.money for pile in player.left] == [20, 8]
    assert player.corpses[0].money == 4
    assert player.body == Body()


class Starving:
    def __init__(self, items: list[Item]) -> None:
        self.fall = Fall(Player(hunger=1.0, items=items))
        self.fall.stand(12, 15, "kapok_walk")
        player, movement, clock = self.fall.player, self.fall.movement, self.fall.world.clock
        self.health = Health(player, movement, clock, die=self.fall.death.die, beds=[])
        self.hunger = Hunger(
            player, movement, clock, pang=lambda damage: self.health.hurt(damage, Vital.HUNGER)
        )

    def minutes(self, minutes: int) -> None:
        for _ in range(minutes):
            self.hunger.tick(60)
            self.health.tick(60)


def test_starving_from_full_health_kills_in_two_sim_hours() -> None:
    starving = Starving([lamp(), BUN])

    starving.minutes(119)
    assert starving.fall.woke == []
    assert starving.fall.player.health == pytest.approx(0.1)
    starving.minutes(1)

    assert [cause for _, cause in starving.fall.woke] == [Vital.HUNGER]
    assert [corpse.items for corpse in starving.fall.player.corpses] == [[BUN]]
    assert starving.fall.player.hunger == 0.75


def test_starving_hurts_regularly_and_stops_when_they_eat() -> None:
    starving = Starving([lamp(), BUN])
    felt = []
    for _ in range(5):
        starving.minutes(12)
        felt.append(starving.fall.player.health)
    assert felt == pytest.approx([0.9, 0.8, 0.7, 0.6, 0.5])

    assert starving.hunger.eat("pork_bun")
    starving.minutes(60)

    assert starving.fall.woke == []
    assert starving.fall.player.health > 0.5


CASES = Path(__file__).parents[3] / "client" / "src" / "ui" / "salvage-panel.cases.json"
WRITE_CASES = "SIMILE_WRITE_SALVAGE_CASES"
HERE = MapTile(map="kapok_walk", x=12, y=15)


def plastic(amount: float, weight: float = 0.5) -> Item:
    return Item(
        id="plastic",
        kind=ItemKind.MATERIAL,
        name="Plastic",
        weight=weight,
        amount=amount,
        material="plastic",
    )


def rounds(amount: float) -> Item:
    return Item(
        id="plastic_rounds",
        kind=ItemKind.ROUNDS,
        name="Plastic rounds",
        weight=0.1,
        amount=amount,
        material="plastic",
    )


def corpse(id: str = "corpse_1", at: MapTile = HERE, **held: Any) -> Corpse:
    fields = {"money": 0.0, "items": [], "bionics": [], **held}
    return Corpse(id=id, owner=PLAYER_ID, at=at, **fields)


class Scene:
    def __init__(self, player: Player, x: float = 12, map: str = "kapok_walk") -> None:
        self.fall = Fall(player)
        self.fall.stand(x, 15, map)
        self.player = player
        self.salvage = Salvage(
            player,
            self.fall.movement,
            self.fall.economy,
            self.fall.world.clock,
            CLINIC_CONFIG.recipes,
        )

    def take(self, **named: Any) -> bool:
        fields = {"corpse": None, "pile": None, "item": None, "index": None, "bionic": None}
        fields |= named
        return self.salvage.take(TakeMessage(**fields))


def ids(player: Player) -> list[str]:
    return [item.id for item in player.items]


def test_a_real_death_gives_up_one_thing_at_a_time_and_goes_with_the_last() -> None:
    fall = Fall(Player(money=31.5, items=[WIRE, lamp(), BUN], body=Body(vertebra=Bionic.DATAJACK)))
    fall.stand(12.3, 15, "kapok_walk")
    fall.death.die(Vital.HEALTH)
    fall.stand(12.3, 15, "kapok_walk")
    player = fall.player
    salvage = Salvage(player, fall.movement, fall.economy, fall.world.clock, CLINIC_CONFIG.recipes)

    def take(**named: Any) -> bool:
        fields = {"corpse": "corpse_1", "pile": None, "item": None, "index": None, "bionic": None}
        fields |= named
        return salvage.take(TakeMessage(**fields))

    assert take(item="pork_bun", index=1)
    assert ids(player) == ["lamp", "pork_bun"]
    assert player.money == 0
    assert take()
    assert player.money == 31.5
    assert not take()
    assert take(bionic=Bionic.DATAJACK)
    assert ids(player) == ["lamp", "pork_bun", "datajack"]
    assert player.items[-1].bionic is Bionic.DATAJACK
    assert [c.items for c in player.corpses] == [[WIRE]]
    assert take(item="copper_wire", index=0)
    assert player.corpses == []
    assert [(e.kind, e.payer, e.payee) for e in fall.economy.ledger.entries] == [
        (Kind.DROPPED, PLAYER, PILES),
        (Kind.RECOVERED, PILES, PLAYER),
    ]
    assert fall.economy.ledger.net(PLAYER) == 0


def test_nothing_goes_past_the_carry_limit_and_what_wont_fit_stays() -> None:
    heavy = Item(id="scrap_steel", kind=ItemKind.SALVAGE, name="Scrap steel", weight=13.0)
    body = corpse(items=[heavy], bionics=[Bionic.BIONIC_LEGS_3])
    scene = Scene(Player(items=[lamp()], carry_limit=5.0, corpses=[body]))

    assert not scene.take(corpse="corpse_1", item="scrap_steel", index=0)
    assert not scene.take(corpse="corpse_1", bionic=Bionic.BIONIC_LEGS_3)

    assert scene.player.corpses == [body]
    assert ids(scene.player) == ["lamp"]


def test_of_a_stack_as_much_as_fits_moves_and_joins_the_one_they_carry() -> None:
    scene = Scene(
        Player(
            items=[plastic(1)],
            carry_limit=2.5,
            corpses=[corpse(items=[plastic(10), rounds(50)])],
        )
    )

    assert scene.take(corpse="corpse_1", item="plastic", index=0)

    assert scene.player.items == [plastic(5)]
    assert scene.player.load == pytest.approx(2.5)
    assert scene.player.corpses[0].items == [plastic(6), rounds(50)]
    assert not scene.take(corpse="corpse_1", item="plastic_rounds", index=1)


def test_two_of_one_bionic_come_out_one_at_a_time() -> None:
    eyes = [Bionic.INFRARED_EYE, Bionic.INFRARED_EYE]
    scene = Scene(Player(corpses=[corpse(bionics=eyes)]))

    assert scene.take(corpse="corpse_1", bionic=Bionic.INFRARED_EYE)
    assert scene.player.corpses[0].bionics == [Bionic.INFRARED_EYE]
    assert scene.take(corpse="corpse_1", bionic=Bionic.INFRARED_EYE)
    assert scene.player.corpses == []


def test_a_salvaged_bionic_they_died_carrying_is_an_item_not_a_bionic() -> None:
    part = Item(
        id="datajack", kind=ItemKind.BIONIC, name="Datajack", weight=0.5, bionic=Bionic.DATAJACK
    )
    scene = Scene(Player(corpses=[corpse(items=[part], bionics=[Bionic.DATAJACK])]))

    assert scene.take(corpse="corpse_1", item="datajack", index=0)

    [left] = scene.player.corpses
    assert (left.items, left.bionics) == ([], [Bionic.DATAJACK])


@pytest.mark.parametrize(
    "where",
    [
        {"x": 14},
        {"map": "metro"},
    ],
    ids=["too_far", "another_map"],
)
def test_a_corpse_or_pile_out_of_reach_gives_nothing(where: dict[str, Any]) -> None:
    pile = Pile(at=HERE, items=[BUN])
    scene = Scene(Player(corpses=[corpse(money=5.0)], left=[pile]), **where)

    assert not scene.take(corpse="corpse_1")
    assert not scene.take(pile=HERE, item="pork_bun", index=0)

    assert scene.player.money == 0
    assert scene.player.left == [pile]


def test_a_corpse_on_another_row_at_the_same_x_is_out_of_reach() -> None:
    above = corpse(at=MapTile(map="kapok_walk", x=12, y=12), money=5.0)
    scene = Scene(Player(corpses=[above]))

    assert not scene.take(corpse="corpse_1")


def test_a_corpse_they_never_had_and_a_thing_that_isnt_on_it_give_nothing() -> None:
    scene = Scene(Player(corpses=[corpse(items=[WIRE])]))

    assert not scene.take(corpse="corpse_9")
    assert not scene.take(corpse="corpse_1")
    assert not scene.take(corpse="corpse_1", item="pork_bun", index=0)
    assert not scene.take(corpse="corpse_1", item="copper_wire", index=1)
    assert not scene.take(corpse="corpse_1", bionic=Bionic.DATAJACK)


def test_a_pile_gives_up_one_thing_at_a_time_and_goes_with_the_last() -> None:
    pile = Pile(at=HERE, items=[WIRE, BUN], money=8.0)
    scene = Scene(Player(left=[pile]))

    assert scene.take(pile=HERE, item="pork_bun", index=1)
    assert scene.player.left == [Pile(at=HERE, items=[WIRE], money=8.0)]
    assert scene.take(pile=HERE)
    assert scene.player.money == 8.0
    assert scene.player.left == [Pile(at=HERE, items=[WIRE])]
    assert scene.take(pile=HERE, item="copper_wire", index=0)
    assert scene.player.left == []


def test_of_two_piles_on_a_tile_it_takes_from_the_oldest() -> None:
    other = MapTile(map="kapok_walk", x=13, y=15)
    piles = [
        Pile(at=other, items=[BUN]),
        Pile(at=HERE, items=[WIRE]),
        Pile(at=HERE, items=[BUN, WIRE]),
    ]
    scene = Scene(Player(left=piles))

    assert not scene.take(pile=HERE, item="pork_bun", index=0)
    assert scene.take(pile=HERE, item="copper_wire", index=0)
    assert scene.player.left == [piles[0], piles[2]]
    assert scene.take(pile=HERE, item="pork_bun", index=0)
    assert scene.player.left == [piles[0], Pile(at=HERE, items=[WIRE])]


def test_of_two_items_with_one_id_it_takes_the_one_at_the_index() -> None:
    worn, loaded = (
        Item(
            id="plastic_pistol",
            kind=ItemKind.WEAPON,
            name="Plastic pistol",
            weight=0.5,
            material="plastic",
            rounds=rounds,
            capacity=6,
            condition=condition,
        )
        for rounds, condition in ((0, 0.1), (6, 1.0))
    )
    scene = Scene(Player(corpses=[corpse(items=[worn, loaded])]))

    assert not scene.take(corpse="corpse_1", item="plastic_pistol", index=2)
    assert scene.take(corpse="corpse_1", item="plastic_pistol", index=1)

    assert scene.player.items[-1] == loaded
    assert scene.player.corpses[0].items == [worn]


def test_a_death_with_nothing_on_them_leaves_no_body_and_uses_no_id() -> None:
    fall = Fall()
    fall.stand(12, 15, "kapok_walk")

    fall.death.die(Vital.HUNGER)

    assert fall.player.corpses == []
    assert fall.player.bodies == 0
    assert fall.woke


def test_a_removed_corpses_id_is_never_used_again_even_across_a_reload() -> None:
    fall = Fall(Player(money=3.0))
    fall.stand(12, 15, "kapok_walk")
    fall.death.die(Vital.HUNGER)
    fall.stand(12, 15, "kapok_walk")
    salvage = Salvage(
        fall.player, fall.movement, fall.economy, fall.world.clock, CLINIC_CONFIG.recipes
    )
    taking = TakeMessage(corpse="corpse_1", pile=None, item=None, index=None, bionic=None)
    assert salvage.take(taking)
    assert fall.player.corpses == []

    loaded = Player.model_validate_json(fall.player.model_dump_json())
    assert loaded.bodies == 1
    loaded.items = [lamp(), WIRE]
    fall.dying(loaded).die(Vital.HUNGER)

    assert [corpse.id for corpse in loaded.corpses] == ["corpse_2"]
    fresh = Player(corpses=[corpse("corpse_2")], bodies=2)
    assert next_corpse(fresh) == "corpse_3"
    assert next_corpse(Player(corpses=[corpse("corpse_2")])) == "corpse_3"


def test_the_last_thing_off_a_corpse_in_the_sewers_leaves_the_lift_open() -> None:
    sewers = MapTile(map="sewers", x=12, y=15)
    scene = Scene(Player(corpses=[corpse(at=sewers, money=5.0)]), map="sewers")
    assert scene.player.lift_open

    assert scene.take(corpse="corpse_1")

    assert scene.player.corpses == []
    assert scene.player.lift_open
    assert Player.model_validate_json(scene.player.model_dump_json()).lift_open


def test_what_they_took_and_what_stayed_survive_a_reload() -> None:
    bionics = [Bionic.SPRING_FEET_2, Bionic.DATAJACK]
    scene = Scene(Player(carry_limit=2.0, corpses=[corpse(bionics=bionics)]))

    assert scene.take(corpse="corpse_1", bionic=Bionic.DATAJACK)
    loaded = Player.model_validate_json(scene.player.model_dump_json())

    assert loaded == scene.player
    assert loaded.items[-1].bionic is Bionic.DATAJACK
    assert loaded.corpses[0].bionics == [Bionic.SPRING_FEET_2]


def test_the_client_is_told_what_each_kind_of_bionic_on_a_corpse_weighs() -> None:
    bodies = [
        corpse("corpse_1", bionics=[Bionic.DATAJACK, Bionic.POWER_CELL]),
        corpse("corpse_2", bionics=[Bionic.DATAJACK]),
    ]
    scene = Scene(Player(corpses=bodies))

    told = scene.salvage.bionics()

    assert [(item.id, item.weight) for item in told] == [
        ("datajack", BIONIC_WEIGHTS[Bionic.DATAJACK]),
        ("power_cell", BIONIC_WEIGHTS[Bionic.POWER_CELL]),
    ]
    assert told[0].name == CLINIC_CONFIG.recipes[Bionic.DATAJACK].name
    nameless = Salvage(Player(), None, None, None, {})  # type: ignore[arg-type]
    assert nameless.item(Bionic.POWER_CELL_2).name == "Power cell 2"


def random_item(rng: random.Random) -> Item:
    kind = rng.choice(["salvage", "salvage", "weapon", "material", "rounds", "food", "free"])
    if kind == "material":
        return plastic(round(rng.uniform(0.1, 20), rng.choice([0, 1, 6])) or 1.0)
    if kind == "rounds":
        return rounds(rng.randint(1, 60))
    if kind == "weapon":
        return Item(
            id="plastic_pistol",
            kind=ItemKind.WEAPON,
            name="Plastic pistol",
            weight=0.5,
            material="plastic",
            rounds=rng.randint(0, 6),
            capacity=6,
            condition=rng.random(),
        )
    if kind == "free":
        return Item(id="note", kind=ItemKind.SALVAGE, name="Note", weight=0.0)
    if kind == "food":
        return BUN
    return rng.choice(
        [WIRE, Item(id="scrap_steel", kind=ItemKind.SALVAGE, name="Scrap steel", weight=9.5)]
    )


def merged(items: list[Item]) -> list[Item]:
    """As the game holds them: one stack of each material or rounds."""
    stacks: set[str] = set()
    kept: list[Item] = []
    for item in items:
        if item.kind in (ItemKind.MATERIAL, ItemKind.ROUNDS):
            if item.id in stacks:
                continue
            stacks.add(item.id)
        kept.append(item)
    return kept


def random_case(rng: random.Random) -> tuple[Player, list[dict[str, Any]]]:
    held = {
        "money": rng.choice([0.0, 0.0, 12.5]),
        "items": merged([random_item(rng) for _ in range(rng.randint(0, 4))]),
        "bionics": rng.sample(list(Bionic), rng.randint(0, 3)),
    }
    if not (held["money"] or held["items"] or held["bionics"]):
        held["money"] = 1.0
    carried = merged([random_item(rng) for _ in range(rng.randint(0, 3))])
    limit = max(sum(item.load for item in carried) + rng.choice([0.0, 0.05, 0.3, 1.0, 5.0]), 0.05)
    player = Player(items=carried, carry_limit=limit, corpses=[corpse(**held)])
    items = held["items"]
    things: list[dict[str, Any]] = [
        {"kind": "item", "id": item.id, "index": index}
        for index, item in enumerate(items)
        if item not in items[:index]
    ]
    things += [{"kind": "bionic", "id": b.value} for b in dict.fromkeys(held["bionics"])]
    if held["money"]:
        things.insert(0, {"kind": "money", "id": "credits"})
    return player, things


def moved(fall: Fall, player: Player, thing: dict[str, Any]) -> float:
    """What the real server moves of `thing`, from a copy of `player`."""
    copy = player.model_copy(deep=True)
    fall.economy.player = copy
    salvage = Salvage(copy, fall.movement, fall.economy, fall.world.clock, CLINIC_CONFIG.recipes)
    item = thing["id"] if thing["kind"] == "item" else None
    bionic = Bionic(thing["id"]) if thing["kind"] == "bionic" else None
    index = thing.get("index")
    taking = TakeMessage(corpse="corpse_1", pile=None, item=item, index=index, bionic=bionic)
    took = salvage.take(taking)
    if not took:
        return 0.0
    assert copy.load <= copy.carry_limit + 1e-9
    if thing["kind"] == "money":
        return copy.money
    amount = lambda p: sum(i.amount for i in p.items if i.id == thing["id"])  # noqa: E731
    return amount(copy) - amount(player)


def salvage_cases() -> list[dict[str, Any]]:
    rng = random.Random(19)
    cases = []
    recipes = CLINIC_CONFIG.recipes
    fall = Fall()
    fall.stand(12, 15, "kapok_walk")
    for _ in range(60):
        player, things = random_case(rng)
        cases.append(
            {
                "player": json.loads(player.model_dump_json()),
                "bionics": [
                    json.loads(item.model_dump_json())
                    for item in Salvage(player, None, None, None, recipes).bionics()  # type: ignore[arg-type]
                ],
                "moves": [thing | {"moved": moved(fall, player, thing)} for thing in things],
            }
        )
    return cases


def test_the_screen_agrees_with_the_server_on_random_cases() -> None:
    """`client/src/ui/salvage-panel.test.ts` reads these cases, the moves the real server made."""
    cases = salvage_cases()
    assert any(thing["moved"] == 0 for case in cases for thing in case["moves"])
    assert any(thing["moved"] > 0 for case in cases for thing in case["moves"])
    if os.environ.get(WRITE_CASES):
        CASES.write_text(json.dumps(cases, separators=(",", ":")) + "\n")
    assert json.loads(CASES.read_text()) == cases, f"Run with {WRITE_CASES}=1 to rewrite {CASES}"
