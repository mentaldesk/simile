from dataclasses import replace

import pytest

from simile.creatures.engine import SEND, Creature, Creatures, Sight
from simile.creatures.kind import Kind
from simile.creatures.ways import Chase, DrawnTo, FleeLight, Patrol, Roost, food, lamp_on
from simile.creatures.ways import lamp as lamp_light
from simile.player.kick import Kick
from simile.protocol import CreatureGoneMessage, CreatureMovedMessage, ServerMessage
from simile.schema import (
    CreatureKind,
    CreatureState,
    Item,
    ItemKind,
    MapTile,
    Player,
    SideFacing,
    TileArea,
    lamp,
)
from simile.world.movement import Point

from .conftest import LOWER, TWO_FLOORS, UPPER, side_view

STEP = 0.1
EAST, WEST = SideFacing.EAST, SideFacing.WEST
STAND_IN = Kind(CreatureKind.RAT, speed=2.0)
"""A creature of no kind in particular, a rat to the client."""
CHASER = replace(STAND_IN, ways=(Chase(sight=20),))
FLIER = Kind(CreatureKind.BAT, flies=True, speed=3.0)
TUNNEL = side_view(*TWO_FLOORS)
ROWS = (
    "####################",
    "#..................#",
    "#..................#",
    "####################",
)
"""One long floor, standing row 2."""
ROW = side_view(*ROWS)


class World:
    """The creatures on a map, with a player who can be anywhere on it."""

    def __init__(self, *towns) -> None:
        self.at: Point | None = None
        self.player = Player()
        self.harmed: list[Kind] = []
        self.sent: list[ServerMessage] = []
        self.creatures = Creatures(
            {town.id: town for town in towns or (TUNNEL,)},
            sense=lambda: Sight(self.player, self.at),
            harm=self.harmed.append,
            send=self.sent.append,
        )

    def spawn(self, kind: Kind, x: int, y: int, map: str = "tunnel", **options) -> Creature:
        return self.creatures.spawn(kind, MapTile(map=map, x=x, y=y), **options)

    def run(self, seconds: float) -> None:
        for _ in range(round(seconds / STEP)):
            self.creatures.tick(STEP)

    def run_until(self, done, seconds: float = 30) -> None:
        for _ in range(round(seconds / STEP)):
            if done():
                return
            self.creatures.tick(STEP)
        assert done(), "never happened"

    def stand(self, x: float, y: float, map: str = "tunnel") -> None:
        self.at = Point(x, y, map)

    def moved(self) -> list[CreatureMovedMessage]:
        return [m for m in self.sent if isinstance(m, CreatureMovedMessage)]


def test_a_patrol_walks_back_and_forth_along_its_floor_pausing_at_each_end() -> None:
    world = World(ROW)
    rat = world.spawn(replace(STAND_IN, ways=(Patrol(pause=1),)), 10, 2, span=3)
    assert rat.route == ((7, 2), (13, 2))

    world.run_until(lambda: rat.cell == (7, 2) and rat.resting)
    assert rat.facing is WEST
    world.run(0.5)
    assert rat.state is CreatureState.IDLE and rat.cell == (7, 2)

    world.run_until(lambda: rat.state is CreatureState.MOVING)
    assert rat.facing is EAST
    world.run_until(lambda: rat.cell == (13, 2) and rat.resting)
    assert {m.creature.state for m in world.moved()} == {CreatureState.IDLE, CreatureState.MOVING}


def test_a_patrol_stays_on_its_own_floor_and_in_its_area() -> None:
    world = World()
    area = TileArea(x=2, y=0, width=8, height=7)
    rat = world.spawn(replace(STAND_IN, ways=(Patrol(),)), 4, LOWER, span=20, area=area)
    assert rat.route == ((2, LOWER), (9, LOWER))
    with pytest.raises(ValueError):
        world.spawn(STAND_IN, 10, LOWER, area=area)


def test_a_spawn_off_the_floor_stands_on_the_floor_under_it() -> None:
    world = World()
    rat = world.spawn(STAND_IN, 9, 1)
    assert rat.cell == (9, UPPER)
    with pytest.raises(ValueError):
        world.spawn(STAND_IN, 0, 0)
    with pytest.raises(ValueError):
        world.creatures.spawn(STAND_IN, MapTile(map="tunnel", x=3, y=LOWER), id=rat.id)


def test_a_chaser_climbs_the_ladder_to_the_player_and_a_kind_that_cannot_climb_waits() -> None:
    world = World()
    rat = world.spawn(CHASER, 3, LOWER)
    dog = world.spawn(replace(CHASER, id=CreatureKind.DOG, climbs=False), 4, LOWER)
    world.stand(5, UPPER)
    rat.seen = dog.seen = ((5, UPPER), 0.0)

    world.run_until(lambda: rat.cell == (5, UPPER))
    assert rat.state is CreatureState.CHASING
    assert dog.y == LOWER and dog.cell == (5, LOWER)
    assert dog.state is CreatureState.IDLE


def test_a_chaser_drops_through_a_hole_to_the_player_below_unless_its_kind_never_drops() -> None:
    world = World()
    rat = world.spawn(replace(CHASER, climbs=False), 10, UPPER)
    bot = world.spawn(replace(CHASER, id=CreatureKind.BOT, climbs=False, drops=False), 9, UPPER)
    world.stand(12, LOWER)
    rat.seen = bot.seen = ((12, LOWER), 0.0)

    world.run_until(lambda: rat.cell == (12, LOWER))
    falls = [m.creature.position for m in world.moved() if m.creature.id == rat.id]
    assert any(p.x == 12 and UPPER < p.y < LOWER for p in falls)
    assert bot.cell == (11, UPPER)


def test_a_kind_that_passes_no_doors_never_steps_on_a_door_s_tile() -> None:
    world = World()
    dog = world.spawn(replace(CHASER, id=CreatureKind.DOG, doors=False), 14, LOWER)
    rat = world.spawn(CHASER, 15, LOWER)
    world.stand(18, LOWER)

    world.run(4)

    assert rat.cell == (18, LOWER)
    assert dog.cell == (17, LOWER)


def test_a_chaser_sees_the_player_only_in_sight_and_not_through_walls() -> None:
    world = World()
    rat = world.spawn(replace(STAND_IN, ways=(Chase(sight=5),)), 3, LOWER)
    world.stand(10, LOWER)
    world.run(1)
    assert rat.cell == (3, LOWER) and rat.state is CreatureState.IDLE

    world.stand(3, UPPER)
    world.run(1)
    assert rat.cell == (3, LOWER), "the slab is between them"

    world.stand(7, LOWER)
    world.run_until(lambda: rat.state is CreatureState.CHASING)


def test_a_chaser_goes_on_to_where_it_last_saw_them_then_gives_up() -> None:
    world = World(ROW)
    rat = world.spawn(replace(STAND_IN, ways=(Chase(sight=4, memory=3), Patrol())), 2, 2, span=0)
    world.stand(5, 2)
    world.run(0.3)
    world.stand(18, 2)

    world.run_until(lambda: rat.cell == (5, 2) and rat.resting)
    assert rat.state is CreatureState.IDLE
    world.run(3)
    assert rat.seen is None


def test_a_chase_only_while_its_condition_holds() -> None:
    world = World(ROW)
    bat = world.spawn(replace(FLIER, ways=(Chase(sight=10, when=lamp_on),)), 3, 1)
    world.stand(8, 2)
    world.run(1)
    assert bat.cell == (3, 1)

    world.player.items = [lamp().model_copy(update={"on": True})]
    world.run_until(lambda: abs(bat.x - 8) < 1)
    assert bat.state in (CreatureState.CHASING, CreatureState.ATTACKING)


def test_a_creature_flees_the_lamp_to_the_dark() -> None:
    dark = side_view(*TWO_FLOORS[:4], dark=TileArea(x=0, y=0, width=20, height=7))
    world = World(dark)
    rat = world.spawn(replace(STAND_IN, ways=(FleeLight(), Patrol())), 8, UPPER, span=0)
    world.stand(5, UPPER)
    world.run(1)
    assert rat.cell == (8, UPPER), "the lamp is off"

    world.player.items = [lamp().model_copy(update={"on": True})]
    world.run_until(lambda: rat.state is CreatureState.FLEEING)
    world.run_until(lambda: rat.resting)
    assert rat.x - 5 > 4.5 or rat.y != UPPER


def test_a_creature_flees_a_lit_stretch_to_the_nearest_dark() -> None:
    lit = (TileArea(x=0, y=0, width=10, height=4),)
    world = World(side_view(*ROWS, dark=TileArea(x=0, y=0, width=20, height=4), lit=lit))
    rat = world.spawn(replace(STAND_IN, ways=(FleeLight(),)), 6, 2)

    world.run_until(lambda: rat.state is CreatureState.FLEEING)
    world.run_until(lambda: rat.resting and rat.state is CreatureState.IDLE)

    assert rat.cell == (10, 2)


def test_a_creature_is_drawn_to_food_the_player_carries() -> None:
    world = World(ROW)
    rat = world.spawn(replace(STAND_IN, ways=(DrawnTo(food, within=8),)), 3, 2)
    world.stand(9, 2)
    world.run(1)
    assert rat.cell == (3, 2)

    world.player.items = [Item(id="ration", kind=ItemKind.FOOD, name="Ration", weight=0.5)]
    world.run_until(lambda: rat.cell == (9, 2))
    assert rat.facing is EAST


def test_a_creature_is_drawn_to_the_lamp_while_it_is_on() -> None:
    world = World(ROW)
    bat = world.spawn(replace(FLIER, ways=(DrawnTo(lamp_light, within=10),)), 3, 1)
    world.stand(9, 2)
    world.run(1)
    assert bat.cell == (3, 1)

    world.player.items = [lamp().model_copy(update={"on": True})]
    world.run_until(lambda: bat.cell == (9, 1) and bat.resting)
    assert bat.state is CreatureState.IDLE


def test_a_bat_roosts_under_the_ceiling_above_where_it_starts() -> None:
    world = World(ROW)
    bat = world.spawn(replace(FLIER, ways=(Roost(when=lambda senses: not senses.lamp),)), 5, 2)
    assert bat.roost == (5, 1)

    world.run_until(lambda: bat.state is CreatureState.ROOSTING)
    shown = world.creatures.shown()[0]
    assert (shown.position.x, shown.position.y) == (5, 0)


def test_in_reach_it_attacks_after_its_windup_and_then_rests() -> None:
    world = World(ROW)
    kind = replace(STAND_IN, ways=(Chase(sight=10),), windup=0.3, rest=1.0)
    rat = world.spawn(kind, 3, 2)
    world.stand(6, 2)

    world.run_until(lambda: rat.state is CreatureState.ATTACKING)
    assert world.harmed == []
    world.run(0.3)
    assert world.harmed == [kind]
    world.run(0.8)
    assert len(world.harmed) == 1
    world.run(0.6)
    assert len(world.harmed) == 2


def test_an_attack_misses_a_player_who_moves_away_or_jumps_over_it() -> None:
    world = World(ROW)
    rat = world.spawn(replace(STAND_IN, ways=(Chase(sight=10),)), 3, 2)
    world.stand(6, 2)
    world.run_until(lambda: rat.state is CreatureState.ATTACKING)
    world.stand(9, 2)
    world.run(0.4)
    assert world.harmed == []

    world.run_until(lambda: rat.state is CreatureState.ATTACKING)
    world.stand(rat.x, 2 - 1.2)
    world.run(0.4)
    assert world.harmed == []


def test_nothing_attacks_without_a_way_that_attacks() -> None:
    world = World(ROW)
    rat = world.spawn(replace(STAND_IN, ways=(DrawnTo(food),)), 3, 2)
    world.player.items = [Item(id="ration", kind=ItemKind.FOOD, name="Ration", weight=0.5)]
    world.stand(4, 2)
    world.run(3)
    assert rat.cell == (4, 2) and world.harmed == []


def kick(x: float, facing: SideFacing, strength: float = 1, y: float = 2) -> Kick:
    return Kick(Point(x, y, "tunnel"), facing, strength)


def test_a_kick_hits_the_nearest_creature_in_front_and_knocks_it_back() -> None:
    world = World(ROW)
    tough = replace(STAND_IN, health=3, knock=2)
    near = world.spawn(tough, 6, 2)
    world.spawn(tough, 7, 2, id="far")
    world.spawn(tough, 4, 2, id="behind")

    hit = world.creatures.kickable(kick(5, EAST))
    assert hit is not None and hit.distance == 1
    hit.land()

    assert near.state is CreatureState.HURT and near.health == 2
    assert near.facing is WEST
    world.run(0.5)
    assert near.cell == (8, 2)
    world.run(0.5)
    assert near.state is CreatureState.IDLE
    assert world.creatures.kickable(kick(5, EAST, y=0.5)) is None, "they're in the air"
    assert world.creatures.kickable(kick(1, EAST)) is None


def test_a_hard_enough_kick_puts_it_down_and_it_comes_back_later() -> None:
    world = World(ROW)
    rat = world.spawn(replace(STAND_IN, health=2), 6, 2, respawn=10)
    world.creatures.kickable(kick(5, EAST, strength=2)).land()

    assert world.sent[-1] == CreatureGoneMessage(creature_id=rat.id)
    assert world.creatures.shown() == []
    assert world.creatures.kickable(kick(5, EAST)) is None
    world.run(9.5)
    assert world.creatures.shown() == []
    world.run(1)
    assert [c.id for c in world.creatures.shown()] == [rat.id]
    assert rat.health == 2 and rat.cell == (6, 2)


def test_each_kind_numbers_its_own_and_never_reuses_a_number() -> None:
    world = World(ROW)
    first = world.spawn(STAND_IN, 6, 2)
    assert world.spawn(FLIER, 3, 1).id == "bat_1"
    world.creatures.kickable(kick(5, EAST)).land()

    assert [world.spawn(STAND_IN, 6, 2).id, first.id] == ["rat_2", "rat_1"]
    world.spawn(STAND_IN, 8, 2, id="rat_3")
    assert world.spawn(STAND_IN, 9, 2).id == "rat_4"


def test_one_that_never_comes_back_is_gone_for_good_and_a_tough_one_shrugs_off_a_kick() -> None:
    world = World(ROW)
    world.spawn(STAND_IN, 6, 2)
    world.creatures.kickable(kick(5, EAST)).land()
    assert world.creatures.all == {}

    dog = world.spawn(replace(STAND_IN, id=CreatureKind.DOG, toughness=1), 4, 2)
    world.creatures.kickable(kick(5, WEST)).land()
    assert dog.health == 1 and dog.state is CreatureState.IDLE


def test_a_roosting_bat_is_out_of_a_kick_s_reach_and_a_low_one_is_not() -> None:
    world = World(ROW)
    bat = world.spawn(FLIER, 6, 2)
    assert world.creatures.kickable(kick(5, EAST)) is not None
    bat.state = CreatureState.ROOSTING
    assert world.creatures.kickable(kick(5, EAST)) is None


def test_it_sends_each_change_of_state_at_once_and_its_moves_every_send_interval() -> None:
    world = World(ROW)
    rat = world.spawn(replace(STAND_IN, ways=(Patrol(pause=1),)), 10, 2, span=6)
    assert world.moved()[0].creature.state is CreatureState.IDLE
    world.sent.clear()

    world.run(0.1)
    world.run_until(lambda: rat.resting)

    moves = world.moved()
    assert moves[0].creature.state is CreatureState.MOVING
    assert moves[-1].creature.state is CreatureState.IDLE
    assert moves[-1].creature.position.x == 4
    assert len(moves) == 6 / STAND_IN.speed / SEND + 1


def test_the_player_is_sensed_only_on_the_creature_s_own_map() -> None:
    other = side_view(*ROWS, map_id="other")
    world = World(ROW, other)
    rat = world.spawn(replace(STAND_IN, ways=(Chase(sight=10),)), 3, 2)
    world.stand(5, 2, map="other")
    world.run(1)
    assert rat.cell == (3, 2)


def test_creatures_are_only_on_side_view_maps() -> None:
    flat = replace(ROW, id="flat", kind=None)
    world = World(flat)
    with pytest.raises(ValueError):
        world.spawn(STAND_IN, 3, 2, map="flat")
