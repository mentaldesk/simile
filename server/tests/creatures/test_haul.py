from simile.creatures.engine import COLLECTING, Creature, Creatures, Sight
from simile.creatures.kind import Kind
from simile.creatures.kinds import BOT, DOG, RAT
from simile.creatures.placing import populate, starting_haul
from simile.creatures.saved import SavedCreature
from simile.schema import CreatureKind, Item, ItemKind, MapTile, Pile, Player
from simile.street.plan import Spawn
from simile.street.sewers import SALVAGE_ITEMS
from simile.world.movement import Point

from .conftest import side_view

STEP = 0.1
ROW = side_view(
    "######################",
    "#....................#",
    "#....................#",
    "######################",
)
"""One long floor, standing row 2."""
WIRE = Item(id="copper_wire", kind=ItemKind.SALVAGE, name="Copper wire", weight=1.5)
VALVE = Item(id="brass_valve", kind=ItemKind.SALVAGE, name="Brass valve", weight=2.0)


class World:
    def __init__(self, lying: dict[tuple[int, int], Item] | None = None) -> None:
        self.lying = dict(lying or {})
        self.piles: list[Pile] = []

        def collect(pickup: str) -> list[Item]:
            cell = next(cell for cell in self.lying if str(cell) == pickup)
            return [self.lying.pop(cell)]

        self.creatures = Creatures(
            {ROW.id: ROW},
            sense=lambda: Sight(Player(), Point(20, 2, ROW.id)),
            salvage=lambda town: {cell: str(cell) for cell in self.lying},
            collect=collect,
            drop=self.piles.append,
        )

    def spawn(self, kind: Kind, x: int, id: str | None = None) -> Creature:
        at = MapTile(map=ROW.id, x=x, y=2)
        return self.creatures.spawn(kind, at, id=id, route=())

    def run(self, seconds: float) -> None:
        for _ in range(round(seconds / STEP)):
            self.creatures.tick(STEP)


def collected_both() -> tuple[World, Creature]:
    world = World({(5, 2): WIRE, (7, 2): VALVE})
    bot = world.spawn(BOT, 3)
    world.run(40)
    assert bot.haul == [WIRE, VALVE] and not world.lying
    return world, bot


def test_a_destroyed_bot_drops_everything_it_collected_as_one_pile_where_it_died() -> None:
    world, bot = collected_both()
    bot.x = 11.4

    world.creatures.hurt(bot, BOT.health)

    at = MapTile(map=ROW.id, x=11, y=2)
    assert world.piles == [Pile(at=at, items=[WIRE, VALVE])]
    assert bot.id not in world.creatures.all


def test_wounds_drop_nothing_until_the_last_round() -> None:
    world, bot = collected_both()

    world.creatures.hurt(bot, BOT.health - 1)
    assert world.piles == [] and bot.haul == [WIRE, VALVE]

    world.creatures.hurt(bot, 1)
    assert len(world.piles) == 1 and bot.haul == []


def test_a_bot_that_collected_nothing_leaves_no_pile() -> None:
    world = World()
    bot = world.spawn(BOT, 3)

    world.creatures.hurt(bot, BOT.health)

    assert world.piles == []
    assert world.creatures.is_gone(bot.id)


def test_what_it_was_still_collecting_stays_lying() -> None:
    world = World({(3, 2): WIRE})
    bot = world.spawn(BOT, 3)
    world.run(COLLECTING / 2)
    assert bot.collecting is not None

    world.creatures.hurt(bot, BOT.health)
    world.run(COLLECTING)

    assert world.piles == [] and world.lying == {(3, 2): WIRE}


def test_a_save_keeps_the_gone_and_the_wounded_and_the_haul_but_not_the_whole() -> None:
    world, hauling = collected_both()
    world.spawn(BOT, 15, id="whole")
    wounded = world.spawn(DOG, 18, id="wounded")
    gone = world.spawn(DOG, 19, id="gone")

    world.creatures.hurt(wounded, 2)
    world.creatures.hurt(gone, DOG.health)

    assert world.creatures.saving() == {
        hauling.id: SavedCreature(haul=[WIRE, VALVE]),
        "wounded": SavedCreature(wounds=2),
        "gone": SavedCreature(gone=True),
    }


def test_a_creature_that_comes_back_isnt_gone_and_a_save_while_its_down_forgets_it() -> None:
    world = World()
    tough = Kind(CreatureKind.RAT, health=3)
    rat = world.creatures.spawn(tough, MapTile(map=ROW.id, x=3, y=2), route=(), respawn=120.0)

    world.creatures.hurt(rat, 3)

    assert rat.down is not None and not world.creatures.is_gone(rat.id)
    assert world.creatures.saving() == {}


def test_spawning_again_takes_up_the_wounds_and_haul_saved_for_it() -> None:
    world = World()
    world.creatures.saved = {"a_bot": SavedCreature(wounds=4, haul=[WIRE])}

    bot = world.spawn(BOT, 3, id="a_bot")

    assert bot.wounds == 4 and bot.haul == [WIRE]
    assert bot.shown().health == 2 / 6
    assert world.creatures.saving() == {"a_bot": SavedCreature(wounds=4, haul=[WIRE])}


def test_more_wounds_saved_than_its_kind_now_takes_leave_it_standing() -> None:
    world = World()
    world.creatures.saved = {"a_dog": SavedCreature(wounds=5)}

    dog = world.spawn(DOG, 3, id="a_dog")

    assert dog.wounds == DOG.health - 1 and dog.shown().health == 1 / 3


def test_what_was_saved_of_a_creature_not_on_these_maps_is_kept() -> None:
    world = World()
    saved = {"elsewhere": SavedCreature(wounds=1), "long_gone": SavedCreature(gone=True)}
    world.creatures.saved = dict(saved)

    assert world.creatures.saving() == saved


def test_placing_skips_those_gone_for_good_and_keeps_placing_a_rat() -> None:
    world = World()
    world.creatures.saved = {"a_bot": SavedCreature(gone=True)}
    placed = [
        (ROW.id, Spawn("a_bot", CreatureKind.BOT, 3, 2, None, None)),
        (ROW.id, Spawn("a_rat", CreatureKind.RAT, 9, 2, None, None)),
    ]

    made = populate(world.creatures, placed, 0, {})

    assert [creature.id for creature in made] == ["a_rat"]
    world.creatures.hurt(made[0], RAT.health)
    world.run(121)
    assert "a_rat" in world.creatures.all and made[0].down is None


def test_what_a_bot_starts_with_joins_what_it_collects_and_all_of_it_drops() -> None:
    world = World({(5, 2): WIRE})
    at = MapTile(map=ROW.id, x=3, y=2)
    bot = world.creatures.spawn(BOT, at, route=(), haul=[VALVE])
    world.run(40)
    assert bot.haul == [VALVE, WIRE]

    world.creatures.hurt(bot, BOT.health)

    assert [pile.items for pile in world.piles] == [[VALVE, WIRE]]


def test_a_save_keeps_a_start_only_with_what_joined_it_and_it_isnt_given_again() -> None:
    world = World({(5, 2): WIRE})
    at = MapTile(map=ROW.id, x=3, y=2)
    bot = world.creatures.spawn(BOT, at, id="a_bot", route=(), haul=[VALVE])
    assert world.creatures.saving() == {}

    world.run(40)
    saved = SavedCreature(haul=[VALVE, WIRE], stocked=True)
    assert world.creatures.saving() == {"a_bot": saved}

    world.creatures.remove(bot.id)
    world.creatures.saved = {"a_bot": saved}
    again = world.creatures.spawn(BOT, at, id="a_bot", route=(), haul=[VALVE])

    assert again.haul == [VALVE, WIRE]
    assert world.creatures.saving() == {"a_bot": saved}


def test_a_wounded_bot_is_saved_with_its_start() -> None:
    world = World()
    at = MapTile(map=ROW.id, x=3, y=2)
    bot = world.creatures.spawn(BOT, at, id="a_bot", route=(), haul=[VALVE])

    world.creatures.hurt(bot, 1)

    saved = SavedCreature(wounds=1, haul=[VALVE], stocked=True)
    assert world.creatures.saving() == {"a_bot": saved}
    world.creatures.remove(bot.id)
    world.creatures.saved = {"a_bot": saved}
    assert world.creatures.spawn(BOT, at, id="a_bot", route=(), haul=[VALVE]).haul == [VALVE]


def test_a_bot_saved_before_starting_hauls_gets_one_ahead_of_what_it_collected() -> None:
    world = World()
    world.creatures.saved = {"a_bot": SavedCreature(wounds=2, haul=[WIRE])}
    at = MapTile(map=ROW.id, x=3, y=2)

    bot = world.creatures.spawn(BOT, at, id="a_bot", route=(), haul=[VALVE])

    assert (bot.wounds, bot.haul, bot.stocked) == (2, [VALVE, WIRE], True)


def test_placing_stocks_bots_from_what_doesnt_lie_on_their_map_and_nothing_else() -> None:
    world = World()
    placed = [
        (ROW.id, Spawn("a_bot", CreatureKind.BOT, 3, 2, None, None)),
        (ROW.id, Spawn("a_rat", CreatureKind.RAT, 9, 2, None, None)),
    ]
    lying = {item.id for item in SALVAGE_ITEMS[1:]}

    bot, rat = populate(world.creatures, placed, 7, {ROW.id: lying})

    assert bot.haul and {item.id for item in bot.haul} == {SALVAGE_ITEMS[0].id}
    assert rat.haul == [] and not rat.stocked


def test_a_starting_haul_is_one_or_two_chosen_by_the_seed() -> None:
    hauls = [[starting_haul(f"bot_{n}", seed, ()) for n in range(20)] for seed in (0, 1)]

    assert hauls[0] == [starting_haul(f"bot_{n}", 0, ()) for n in range(20)]
    assert hauls[0] != hauls[1]
    assert {len(haul) for haul in hauls[0]} == {1, 2}
    assert all(item in SALVAGE_ITEMS for haul in hauls[0] for item in haul)


def test_with_everything_lying_on_its_map_a_bot_starts_with_nothing() -> None:
    assert starting_haul("a_bot", 0, {item.id for item in SALVAGE_ITEMS}) == []


def test_a_starting_haul_is_these_items_in_any_process_until_the_list_of_kinds_changes() -> None:
    def ids(lying: set[str]) -> list[str]:
        return [item.id for item in starting_haul("metro_bot_1", 0, lying)]

    assert ids(set()) == ["copper_coil", "float_valve"]
    assert ids({"copper_coil", "pump_impeller"}) == ["brass_fitting", "filter_mesh"]
