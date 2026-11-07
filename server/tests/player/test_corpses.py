from datetime import UTC, datetime
from pathlib import Path

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
from simile.protocol import Vital
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


def test_a_death_with_nothing_on_them_still_leaves_a_corpse() -> None:
    fall = Fall()
    fall.stand(12, 15, "kapok_walk")

    fall.death.die(Vital.HUNGER)

    assert fall.player.corpses == [
        Corpse(
            id="corpse_1",
            owner=PLAYER_ID,
            at=MapTile(map="kapok_walk", x=12, y=15),
            money=0,
            items=[],
            bionics=[],
        )
    ]


@pytest.mark.parametrize(
    ("x", "y", "ground"),
    [(17.2, 5.6, (17, 8)), (22.4, 5, (22, 15)), (3, 13.5, (3, 15))],
    ids=["over_a_roof", "over_a_gap", "on_a_ladder"],
)
def test_a_corpse_falls_to_the_ground_below(x: float, y: float, ground: tuple[int, int]) -> None:
    fall = Fall()
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
    fall.dying(loaded).die(Vital.POWER)

    reloaded = Player.model_validate_json(loaded.model_dump_json())
    assert [corpse.id for corpse in reloaded.corpses] == ["corpse_1", "corpse_2"]
    assert reloaded.corpses[0] == fall.player.corpses[0]


def test_corpses_survive_the_world_being_saved_and_loaded(tmp_path: Path) -> None:
    fall = Fall(Player(money=10, items=[lamp(), WIRE], body=FITTED))
    fall.stand(12, 15, "kapok_walk")
    fall.death.die(Vital.HUNGER)
    fall.stand(30, 15, "kapok_walk")
    fall.death.die(Vital.HEALTH)
    path = tmp_path / "simile.db"

    with MemoryStore(path) as memory, WorldStore(memory) as store:
        store.save(capture(fall.behaviour, player=fall.player))
    with MemoryStore(path) as memory, WorldStore(memory) as store:
        loaded = store.load()

    assert loaded is not None
    assert loaded.player == fall.player
    assert [corpse.id for corpse in loaded.player.corpses] == ["corpse_1", "corpse_2"]


def test_the_id_skips_any_already_taken() -> None:
    at = MapTile(map="metro", x=3, y=15)
    corpse = Corpse(id="corpse_2", owner=PLAYER_ID, at=at, money=0, items=[], bionics=[])

    assert next_corpse([corpse]) == "corpse_3"
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


def corpse(id: str, x: int = 12, **held: object) -> Corpse:
    at = MapTile(map="kapok_walk", x=x, y=15)
    return Corpse(
        **{"id": id, "owner": PLAYER_ID, "at": at, "money": 0.0, "items": [], "bionics": [], **held}
    )


def salvaging(player: Player) -> tuple[Fall, Pickups]:
    fall = Fall(player)
    fall.stand(12, 15, "kapok_walk")
    return fall, Pickups(player, fall.movement, fall.economy, fall.world.clock)


def press(fall: Fall, pickups: Pickups) -> None:
    salvage = Salvage(fall.player, fall.economy, fall.world.clock, CLINIC_CONFIG.recipes)
    pickups.pick_up([salvage.claim])


def graded(bionic: Bionic) -> Item:
    return Salvage(Player(), None, None, CLINIC_CONFIG.recipes).item(bionic)  # type: ignore[arg-type]


def test_every_bionic_comes_out_with_its_recipes_name_a_weight_and_its_grade() -> None:
    assert set(BIONIC_WEIGHTS) == set(Bionic)
    item = graded(Bionic.BIONIC_LEGS_2)
    assert item.id == item.bionic == Bionic.BIONIC_LEGS_2
    assert (item.kind, item.name, item.weight) == (ItemKind.BIONIC, "Bionic legs, grade 2", 7.0)


def test_e_at_their_corpse_takes_the_money_items_and_bionics_of_a_real_death() -> None:
    fall = Fall(Player(money=31.5, items=[WIRE, lamp(), BUN], body=FITTED))
    fall.stand(12.3, 15, "kapok_walk")
    fall.death.die(Vital.HEALTH)
    fall.stand(12.3, 15, "kapok_walk")
    player = fall.player
    assert player.money == 0

    press(fall, Pickups(player, fall.movement, fall.economy, fall.world.clock))

    assert player.money == 31.5
    assert [item.id for item in player.items] == [
        "lamp",
        "copper_wire",
        "pork_bun",
        "bionic_legs_2",
        "datajack",
        "power_cell",
    ]
    [left] = player.corpses
    assert (left.money, left.items, left.bionics) == (0, [], [])
    assert [(e.kind, e.payer, e.payee) for e in fall.economy.ledger.entries] == [
        (Kind.DROPPED, PLAYER, PILES),
        (Kind.RECOVERED, PILES, PLAYER),
    ]
    assert fall.economy.ledger.net(PLAYER) == 0


def test_what_doesnt_fit_stays_on_the_corpse_until_they_can_carry_it() -> None:
    heavy = Item(id="scrap_steel", kind=ItemKind.SALVAGE, name="Scrap steel", weight=13.0)
    held = {
        "items": [heavy, WIRE],
        "bionics": [Bionic.BIONIC_LEGS_3, Bionic.DATAJACK],
        "money": 5.0,
    }
    fall, pickups = salvaging(Player(items=[lamp(), BUN], carry_limit=5.0))
    fall.player.corpses = [corpse("corpse_1", **held)]

    press(fall, pickups)

    player = fall.player
    assert [item.id for item in player.items] == ["lamp", "pork_bun", "copper_wire", "datajack"]
    assert player.load <= player.carry_limit
    assert player.money == 5.0
    [left] = player.corpses
    assert (left.money, left.items, left.bionics) == (0, [heavy], [Bionic.BIONIC_LEGS_3])

    press(fall, pickups)
    assert player.corpses == [left]

    player.carry_limit = 15.0
    press(fall, pickups)
    assert [item.id for item in player.items][-1] == "bionic_legs_3"
    assert player.corpses[0].items == [heavy]
    assert player.corpses[0].bionics == []


def test_items_use_up_the_room_before_a_bionic_is_weighed() -> None:
    fall, pickups = salvaging(Player(carry_limit=3.0))
    fall.player.corpses = [corpse("corpse_1", items=[WIRE], bionics=[Bionic.POWER_CELL])]

    press(fall, pickups)

    assert [item.id for item in fall.player.items] == ["lamp", "copper_wire"]
    assert fall.player.load <= fall.player.carry_limit
    assert fall.player.corpses[0].bionics == [Bionic.POWER_CELL]


def test_a_stack_on_a_corpse_joins_the_one_they_carry() -> None:
    plastic = Item(
        id="plastic",
        kind=ItemKind.MATERIAL,
        name="Plastic",
        weight=0.1,
        amount=2.0,
        material="plastic",
    )
    fall, pickups = salvaging(Player(items=[lamp(), plastic]))
    fall.player.corpses = [corpse("corpse_1", items=[plastic], bionics=[Bionic.DATAJACK])]

    press(fall, pickups)

    assert [(item.id, item.amount) for item in fall.player.items] == [
        ("lamp", 1),
        ("plastic", 4),
        ("datajack", 1),
    ]


def test_of_two_corpses_on_one_tile_the_older_goes_first_and_the_next_e_takes_the_newer() -> None:
    fall, pickups = salvaging(Player())
    fall.player.corpses = [
        corpse("corpse_1", items=[WIRE]),
        corpse("corpse_2", items=[BUN]),
    ]

    press(fall, pickups)
    assert [item.id for item in fall.player.items] == ["lamp", "copper_wire"]
    assert fall.player.corpses[1].items == [BUN]

    press(fall, pickups)
    assert [item.id for item in fall.player.items] == ["lamp", "copper_wire", "pork_bun"]


def test_an_older_corpse_they_cant_carry_from_doesnt_hide_a_newer_one() -> None:
    fall, pickups = salvaging(Player(carry_limit=2.0))
    fall.player.corpses = [
        corpse("corpse_1", bionics=[Bionic.BIONIC_LEGS]),
        corpse("corpse_2", bionics=[Bionic.DATAJACK]),
    ]

    press(fall, pickups)

    assert [item.id for item in fall.player.items] == ["lamp", "datajack"]
    assert fall.player.corpses[0].bionics == [Bionic.BIONIC_LEGS]


def test_an_emptied_corpse_stays_and_e_goes_past_it_to_a_pile() -> None:
    fall, pickups = salvaging(Player())
    empty = corpse("corpse_1")
    pile = Pile(at=MapTile(map="kapok_walk", x=13, y=15), items=[BUN])
    fall.player.corpses = [empty]
    fall.player.left = [pile]

    press(fall, pickups)

    assert fall.player.corpses == [empty]
    assert [item.id for item in fall.player.items] == ["lamp", "pork_bun"]


def test_a_pile_goes_ahead_of_a_corpse_as_near_and_a_corpse_ahead_of_a_further_pile() -> None:
    fall, pickups = salvaging(Player())
    fall.player.corpses = [corpse("corpse_1", items=[WIRE])]
    fall.player.left = [Pile(at=MapTile(map="kapok_walk", x=12, y=15), items=[BUN])]

    press(fall, pickups)
    assert [item.id for item in fall.player.items] == ["lamp", "pork_bun"]

    fall.player.left = [Pile(at=MapTile(map="kapok_walk", x=13, y=15), items=[BUN])]
    press(fall, pickups)
    assert [item.id for item in fall.player.items] == ["lamp", "pork_bun", "copper_wire"]
    assert len(fall.player.left) == 1


@pytest.mark.parametrize(
    "far",
    [
        corpse("corpse_1", x=14, items=[WIRE]),
        Corpse(
            id="corpse_1",
            owner=PLAYER_ID,
            at=MapTile(map="metro", x=12, y=15),
            money=0.0,
            items=[WIRE],
            bionics=[],
        ),
    ],
)
def test_a_corpse_out_of_reach_or_on_another_map_gives_nothing(far: Corpse) -> None:
    fall, pickups = salvaging(Player())
    fall.player.corpses = [far]

    press(fall, pickups)

    assert fall.player.corpses == [far]
    assert [item.id for item in fall.player.items] == ["lamp"]


def test_a_pile_nearer_than_a_corpse_goes_first() -> None:
    fall, pickups = salvaging(Player())
    fall.stand(12.4, 15, "kapok_walk")
    fall.player.corpses = [corpse("corpse_1", x=13, items=[WIRE])]
    fall.player.left = [Pile(at=MapTile(map="kapok_walk", x=12, y=15), items=[BUN])]

    press(fall, pickups)

    assert [item.id for item in fall.player.items] == ["lamp", "pork_bun"]
    assert fall.player.corpses[0].items == [WIRE]


def test_a_corpse_on_another_row_at_the_same_x_is_out_of_reach() -> None:
    fall, pickups = salvaging(Player())
    above = corpse("corpse_1", at=MapTile(map="kapok_walk", x=12, y=12), items=[WIRE])
    fall.player.corpses = [above]

    press(fall, pickups)

    assert fall.player.corpses == [above]
    assert [item.id for item in fall.player.items] == ["lamp"]


def test_what_they_took_and_what_stayed_survive_a_reload() -> None:
    fall, pickups = salvaging(Player(carry_limit=2.0))
    fall.player.corpses = [corpse("corpse_1", bionics=[Bionic.SPRING_FEET_2, Bionic.DATAJACK])]

    press(fall, pickups)
    loaded = Player.model_validate_json(fall.player.model_dump_json())

    assert loaded == fall.player
    assert loaded.items[-1].bionic is Bionic.DATAJACK
    assert loaded.corpses[0].bionics == [Bionic.SPRING_FEET_2]
