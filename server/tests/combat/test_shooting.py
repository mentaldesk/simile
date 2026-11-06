import pytest

from simile.combat.shooting import LASTS, RANGE, Shooting
from simile.creatures.engine import Creature, Creatures
from simile.creatures.kind import Kind
from simile.creatures.kinds import BAT, BOT, DOG, RAT
from simile.protocol import (
    CreatureGoneMessage,
    CreatureHitMessage,
    CreatureMovedMessage,
    ServerMessage,
)
from simile.schema import (
    PLAYER_ID,
    CreatureKind,
    CreatureState,
    Item,
    ItemKind,
    MapTile,
    Material,
    Player,
    SideFacing,
    lamp,
)
from simile.world.map import MapKind, TownMap
from simile.world.movement import Point

EAST, WEST = SideFacing.EAST, SideFacing.WEST
STILL = Kind(CreatureKind.RAT)
"""A target that stays where it's put."""
CHEST_HIGH = Kind(CreatureKind.BAT, flies=True)


def side_view(*rows: str) -> TownMap:
    width, height = len(rows[0]), len(rows)
    solids = tuple(tuple(cell == "#" for cell in row) for row in rows)
    blocked = tuple(
        tuple(cell == "#" or y + 1 >= height or rows[y + 1][x] != "#" for x, cell in enumerate(row))
        for y, row in enumerate(rows)
    )
    return TownMap("tunnel", width, height, blocked, (), kind=MapKind.STREET, solids=solids)


ROW = side_view(
    "##############################",
    "#............................#",
    "#............................#",
    "#............................#",
    "##############################",
)
"""One long floor, standing row 3."""
FLOOR = 3
WALL = side_view(
    "####################",
    "#..................#",
    "#......#...........#",
    "#......#...........#",
    "####################",
)
"""A wall two high at x 7."""
LOW_WALL = side_view(
    "####################",
    "#..................#",
    "#..................#",
    "#......#...........#",
    "####################",
)
"""A wall one high at x 7."""


def pistol(rounds: int = 6, condition: float = 1.0) -> Item:
    return Item(
        id="pistol",
        kind=ItemKind.WEAPON,
        name="Plastic pistol",
        weight=0.5,
        material=Material.PLASTIC,
        rounds=rounds,
        capacity=6,
        condition=condition,
    )


def rounds(amount: float) -> Item:
    return Item(
        id="rounds",
        kind=ItemKind.ROUNDS,
        name="Plastic rounds",
        weight=0.02,
        amount=amount,
        material=Material.PLASTIC,
    )


class Where:
    """Stands in for `Movement`: the player where the server last kept them."""

    def __init__(self, at: Point | None) -> None:
        self.at = at

    def entities(self) -> dict[str, Point]:
        return {PLAYER_ID: self.at} if self.at is not None else {}


class World:
    def __init__(self, town: TownMap = ROW, *items: Item, at: float = 3.0) -> None:
        self.sent: list[ServerMessage] = []
        self.player = Player(items=[lamp(), *(items or (pistol(),))])
        self.where = Where(Point(at, FLOOR, town.id))
        self.creatures = Creatures({town.id: town}, send=self.sent.append)
        self.shooting = Shooting(self.player, self.where, self.creatures)  # type: ignore[arg-type]

    def spawn(self, kind: Kind, x: int, y: int = FLOOR, **options) -> Creature:
        return self.creatures.spawn(kind, MapTile(map="tunnel", x=x, y=y), **options)

    @property
    def weapon(self) -> Item:
        return next(item for item in self.player.items if item.kind is ItemKind.WEAPON)

    def stack(self) -> list[float]:
        return [item.amount for item in self.player.items if item.kind is ItemKind.ROUNDS]

    def hits(self) -> list[str]:
        return [m.creature_id for m in self.sent if isinstance(m, CreatureHitMessage)]


@pytest.mark.parametrize(
    ("kind", "shots"),
    [(RAT, 1), (DOG, 3), (BOT, 6), (BAT, 1)],
    ids=["rat", "dog", "bot", "bat"],
)
def test_each_kind_takes_its_rounds_to_kill(kind: Kind, shots: int) -> None:
    world = World()
    creature = world.spawn(kind, 8)

    for left in range(shots, 1, -1):
        assert world.shooting.fire(EAST)
        assert creature.id in world.creatures.all, f"{left} rounds from dead"
    assert world.shooting.fire(EAST)

    assert creature.id not in world.creatures.all
    assert world.sent[-1] == CreatureGoneMessage(creature_id=creature.id)
    assert world.hits() == [creature.id] * shots


def test_a_hit_tells_the_client_first_then_sends_the_lower_health_at_once() -> None:
    world = World()
    dog = world.spawn(DOG, 8)
    world.sent.clear()

    world.shooting.fire(EAST)
    assert world.sent[0] == CreatureHitMessage(creature_id=dog.id)
    moved = world.sent[1]
    assert isinstance(moved, CreatureMovedMessage)
    assert moved.creature.health == pytest.approx(2 / 3)
    assert world.creatures.shown()[0].health == pytest.approx(2 / 3)

    world.shooting.fire(EAST)
    moved = world.sent[-1]
    assert isinstance(moved, CreatureMovedMessage)
    assert moved.creature.health == pytest.approx(1 / 3)


def test_a_hit_on_one_on_the_move_isnt_held_back_by_the_throttle() -> None:
    world = World()
    dog = world.spawn(DOG, 8, route=[(20, FLOOR)])
    world.creatures.tick(0.1)
    world.creatures.tick(0.1)
    assert not dog.resting
    world.sent.clear()

    world.shooting.fire(EAST)

    moved = world.sent[-1]
    assert isinstance(moved, CreatureMovedMessage)
    assert moved.creature.health < 1


def test_a_full_health_one_leaves_its_health_out_of_the_message() -> None:
    world = World()
    rat = world.spawn(RAT, 8)

    assert "health" not in rat.shown().model_dump(exclude_none=True)


def test_a_shot_goes_only_the_way_they_face() -> None:
    world = World(at=10.0)
    east, west = world.spawn(STILL, 14), world.spawn(STILL, 6)

    world.shooting.fire(WEST)
    assert world.hits() == [west.id]
    world.shooting.fire(EAST)
    assert world.hits() == [west.id, east.id]


def test_a_shot_takes_only_the_first_creature_in_line() -> None:
    world = World()
    world.spawn(STILL, 12)
    near = world.spawn(STILL, 6)

    world.shooting.fire(EAST)

    assert world.hits() == [near.id]


def test_a_shot_reaches_only_as_far_as_its_range() -> None:
    world = World()
    far = world.spawn(STILL, 3 + RANGE + 1)
    assert world.shooting.fire(EAST)
    assert world.hits() == []
    assert world.weapon.rounds == 5, "a miss still uses a round"

    near = world.spawn(STILL, 3 + RANGE)
    world.shooting.fire(EAST)
    assert world.hits() == [near.id]
    assert far.id in world.creatures.all


def test_a_wall_stops_a_shot_and_it_still_uses_a_round() -> None:
    world = World(WALL)
    world.spawn(STILL, 10)

    assert world.shooting.fire(EAST)

    assert world.hits() == []
    assert world.weapon.rounds == 5


def test_a_wall_only_stops_the_row_its_in() -> None:
    world = World(LOW_WALL)
    world.spawn(STILL, 10)
    bat = world.spawn(CHEST_HIGH, 10, FLOOR - 1)

    world.shooting.fire(EAST)

    assert world.hits() == [bat.id]


def test_a_shot_hits_from_their_feet_to_their_chest_and_no_higher() -> None:
    world = World()
    world.spawn(CHEST_HIGH, 8, FLOOR - 2)
    world.shooting.fire(EAST)
    assert world.hits() == []

    bat = world.spawn(CHEST_HIGH, 9, FLOOR - 1)
    world.shooting.fire(EAST)
    assert world.hits() == [bat.id]


def test_a_jump_lifts_the_shot_over_a_rat() -> None:
    world = World()
    world.spawn(STILL, 8)
    world.where.at = Point(3.0, FLOOR - 1.0, "tunnel")

    world.shooting.fire(EAST)

    assert world.hits() == []


def test_a_creature_down_until_it_comes_back_doesnt_stop_a_shot() -> None:
    world = World()
    down = world.spawn(RAT, 6, respawn=120)
    behind = world.spawn(STILL, 8)
    world.shooting.fire(EAST)
    assert down.down is not None
    world.sent.clear()

    world.shooting.fire(EAST)

    assert [m.creature_id for m in world.sent if isinstance(m, CreatureHitMessage)] == [behind.id]


def test_one_back_after_going_down_is_whole() -> None:
    world = World()
    dog = world.spawn(DOG, 8, respawn=10)
    for _ in range(3):
        world.shooting.fire(EAST)
    assert dog.down is not None

    world.creatures.tick(10.5)

    assert dog.down is None and dog.state is CreatureState.IDLE
    assert dog.shown().health == 1


def test_an_empty_magazine_doesnt_fire() -> None:
    world = World(ROW, pistol(rounds=0))
    world.spawn(STILL, 8)

    assert not world.shooting.fire(EAST)

    assert world.hits() == []
    assert world.weapon.condition == 1


def test_it_fires_the_first_loaded_weapon() -> None:
    world = World(ROW, pistol(rounds=0), pistol(rounds=2))

    assert world.shooting.fire(EAST)

    weapons = [item.rounds for item in world.player.items if item.kind is ItemKind.WEAPON]
    assert weapons == [0, 1]


def test_no_weapon_doesnt_fire() -> None:
    world = World(ROW, rounds(6))

    assert not world.shooting.fire(EAST)
    assert world.stack() == [6]


def test_nowhere_to_fire_from_uses_no_round() -> None:
    world = World()
    world.where.at = None

    assert not world.shooting.fire(EAST)
    assert world.weapon.rounds == 6


def test_reload_fills_it_from_the_stack_and_a_stack_it_empties_is_gone() -> None:
    world = World(ROW, pistol(rounds=2), rounds(6))

    assert world.shooting.reload()
    assert world.weapon.rounds == 6
    assert world.stack() == [2]

    world.player.items = [lamp(), pistol(rounds=2), rounds(2)]
    assert world.shooting.reload()
    assert world.weapon.rounds == 4
    assert world.stack() == []


def test_reload_takes_from_more_than_one_stack() -> None:
    world = World(ROW, pistol(rounds=0), rounds(2), rounds(2), rounds(5))

    assert world.shooting.reload()

    assert world.weapon.rounds == 6
    assert world.stack() == [3]


def test_reload_with_no_rounds_or_no_room_or_no_weapon_does_nothing() -> None:
    assert not World(ROW, pistol(rounds=2)).shooting.reload()
    assert not World(ROW, pistol(), rounds(6)).shooting.reload()
    assert not World(ROW, rounds(6)).shooting.reload()


def test_reload_goes_to_the_first_weapon_with_room() -> None:
    world = World(ROW, pistol(), pistol(rounds=0, condition=0.0), pistol(rounds=1), rounds(1))

    assert world.shooting.reload()

    weapons = [item.rounds for item in world.player.items if item.kind is ItemKind.WEAPON]
    assert weapons == [6, 0, 2]


def test_loaded_rounds_are_whole_numbers_that_survive_a_save() -> None:
    world = World(ROW, pistol(rounds=2), rounds(6))
    world.shooting.reload()
    world.shooting.fire(EAST)

    saved = Player.model_validate_json(world.player.model_dump_json())

    assert saved.items == world.player.items
    assert isinstance(saved.items[1].rounds, int)
    assert saved.items[2].amount == 2


def test_a_plastic_pistol_wears_out_after_thirty_rounds_exactly() -> None:
    lasts = LASTS[Material.PLASTIC]
    world = World(ROW, pistol(), rounds(100))

    for fired in range(1, lasts + 1):
        if not world.weapon.rounds:
            assert world.shooting.reload()
        assert world.shooting.fire(EAST)
        assert world.weapon.condition == pytest.approx(1 - fired / lasts)

    assert world.weapon.condition == 0
    assert not world.shooting.fire(EAST), "a 31st round"


def test_a_worn_out_pistol_doesnt_fire_or_reload_and_keeps_what_it_has_loaded() -> None:
    world = World(ROW, pistol(rounds=3, condition=0.0), rounds(6))
    world.spawn(STILL, 8)

    assert not world.shooting.fire(EAST)
    assert not world.shooting.reload()

    assert world.hits() == []
    assert world.weapon.rounds == 3
    assert world.stack() == [6]
