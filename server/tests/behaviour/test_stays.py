import math
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from simile.behaviour import DEFAULT_CONFIG, Activity, Behaviour, BehaviourConfig, Goal, Need
from simile.behaviour.config import LOOPS
from simile.behaviour.scoring import (
    Places,
    Situation,
    best_per_activity,
    boring,
    new,
    rising,
    scores,
)
from simile.npc import load_npcs
from simile.schema import CoreValue, Craft, MapTile, Medium, Npc, Traits
from simile.sim import STEP, Clock, EntityMoved, FakeWallClock, World
from simile.world import Movement, Point
from simile.world.map import SpotKind, load_maps, with_every_location

MAPS = load_maps()
TEMPLATE = load_npcs()[0]
DAY = datetime(2026, 1, 1, tzinfo=UTC)
A = Activity
PARK = Goal(A.PARK, "park")
GALLERY = Goal(A.GALLERY, "gallery")
STEADY = DEFAULT_CONFIG.model_copy(update={"temperature": 0.0})
STAY_PUT = STEADY.model_copy(update={"switch": 100.0, "new_spot": 0.0})
CONTENT = {need: 0.0 for need in Need}
NO_WORK = {"workplace": None, "shifts": [], "pay": None}


def make_npc(id: str, home: str, **values: float) -> Npc:
    scores = {value: values.get(value.value, 0.5) for value in CoreValue}
    return TEMPLATE.model_copy(
        update={"id": id, "name": id.title(), "home": home, "values": scores, "craft": None}
        | NO_WORK
    )


ANA = make_npc("ana", "house_1")
BEN = make_npc("ben", "house_2")


class Village:
    def __init__(
        self,
        npcs: list[Npc],
        *,
        config: BehaviourConfig = STEADY,
        traits: dict[str, Traits] | None = None,
    ) -> None:
        self.world = World(Clock(DAY + timedelta(hours=11)), FakeWallClock())
        self.movement = Movement(MAPS, self.world.bus)
        self.behaviour = Behaviour(
            self.world.clock,
            self.world.bus,
            self.movement,
            npcs,
            config=config,
            seed=0,
            traits=traits,
        )
        self.moves: list[EntityMoved] = []
        self.world.bus.subscribe(EntityMoved, self.moves.append)
        self.world.loop.register(self.behaviour)
        self.world.loop.register(self.movement)
        self.behaviour.start()

    @property
    def now(self) -> datetime:
        return self.world.clock.now

    def run(self, *, minutes: float) -> None:
        for _ in range(round(minutes * 60 / STEP)):
            self.world.loop.tick()

    def run_until(self, done: Callable[[], bool], *, minutes: float = 30) -> None:
        end = self.now + timedelta(minutes=minutes)
        while not done():
            assert self.now < end, "ran out of time"
            self.world.loop.tick()

    def stay(
        self, npc: str, goal: Goal, *, ago: float = 0, left: float = 60, **needs: float
    ) -> None:
        """Put them `ago` minutes into a stay at `goal` with `left` minutes to its longest, with
        nothing needed but the needs given."""
        assert goal.target is not None
        self.movement.place(npc, goal.target)
        levels = CONTENT | {Need(need): level for need, level in needs.items()}
        since, until = self.now - timedelta(minutes=ago), self.now + timedelta(minutes=left)
        self.behaviour.restore(npc, goal, levels, since, until, {})

    def need(self, npc: str, need: Need) -> float:
        return self.behaviour.needs(npc)[need]


def test_a_stay_ends_early_once_staying_is_worth_less_than_the_best_other_option() -> None:
    village = Village([ANA])
    village.stay("ana", PARK, left=50, hunger=0.8)
    shortest = DEFAULT_CONFIG.dwell[A.PARK][0]

    village.run(minutes=shortest - 1)
    assert village.behaviour.goal("ana") == PARK

    village.run(minutes=DEFAULT_CONFIG.reconsider + 1)
    assert village.behaviour.goal("ana") != PARK
    assert village.need("ana", Need.HUNGER) < DEFAULT_CONFIG.urgency[Need.HUNGER].critical


def test_a_stay_that_still_pays_carries_on_past_its_shortest() -> None:
    village = Village([ANA])
    village.stay("ana", PARK, left=50, relaxation=1.0)

    village.run(minutes=DEFAULT_CONFIG.dwell[A.PARK][0] + 10)

    assert village.behaviour.goal("ana") == PARK
    assert village.need("ana", Need.RELAXATION) < 0.6


def test_boredom_rises_only_while_nothing_is_being_relieved() -> None:
    village = Village([ANA, BEN], config=STAY_PUT)
    village.stay("ana", PARK)
    village.stay("ben", PARK, relaxation=1.0)

    village.run(minutes=20)

    assert village.need("ana", Need.BOREDOM) > 0.1
    assert village.need("ben", Need.BOREDOM) < 0.01


def test_a_stay_bores_less_the_more_it_relieves() -> None:
    needs = CONTENT | {Need.RELAXATION: 0.5}

    nothing = boring(needs, {}, DEFAULT_CONFIG)
    a_little = boring(needs, {Need.RELAXATION: -0.2}, DEFAULT_CONFIG)
    plenty = boring(needs, {Need.RELAXATION: -2.0}, DEFAULT_CONFIG)

    assert nothing == 1 > a_little > plenty == 0


def test_somewhere_new_eases_boredom_and_somewhere_familiar_does_not() -> None:
    village = Village([ANA], config=STEADY.model_copy(update={"base": {A.PARK: 10.0}}))
    village.behaviour.minds["ana"].needs[Need.BOREDOM] = 0.6
    mind = village.behaviour.minds["ana"]

    village.run_until(lambda: mind.goal == PARK and mind.walk is None)

    expected = 0.6 - DEFAULT_CONFIG.novelty
    assert village.need("ana", Need.BOREDOM) == pytest.approx(expected, abs=0.05)
    assert not new(PARK, PARK) and new(GALLERY, PARK)
    assert not new(Goal(A.HOME, "house_1"), PARK)


def test_adventure_freedom_and_open_mindedness_bore_faster_and_peace_of_mind_slower() -> None:
    def bored(**values: float) -> float:
        return rising(Need.BOREDOM, make_npc("x", "house_1", **values).values)

    neutral = bored()

    assert bored(adventure=0.9, freedom=0.9, open_mindedness=0.9) > 1.3 * neutral
    assert bored(peace_of_mind=0.9, tradition=0.9) < neutral
    assert bored(adventure=0.0, peace_of_mind=1.0, tradition=1.0) >= 0


@pytest.mark.parametrize(
    "goal",
    [
        PARK,
        GALLERY,
        Goal(A.NEWS, "terminal_2"),
        Goal(A.COFFEE_SHOP, "coffee_shop"),
        Goal(A.HOME, "house_1"),
    ],
)
def test_relaxation_spots_meet_relaxation(goal: Goal) -> None:
    village = Village([ANA], config=STAY_PUT)
    village.stay("ana", goal, relaxation=0.8)

    village.run(minutes=10)

    assert village.need("ana", Need.RELAXATION) < 0.75


def test_work_and_making_things_wear_them_out() -> None:
    village = Village([ANA, BEN], config=STAY_PUT)
    village.stay("ana", Goal(A.WORK, "maker_space"))
    village.stay("ben", Goal(A.MAKER_SPACE, "maker_space"))

    village.run(minutes=30)

    assert village.need("ana", Need.RELAXATION) > village.need("ben", Need.RELAXATION) > 0


def test_busy_places_wear_out_the_unsociable_more() -> None:
    crowd = [make_npc(f"crowd{n}", f"house_{n + 3}") for n in range(3)]
    loner, mixer = make_npc("loner", "house_1"), make_npc("mixer", "house_2")
    traits = {"loner": Traits(sociability=0.1), "mixer": Traits(sociability=0.9)}
    village = Village([loner, mixer, *crowd], config=STAY_PUT, traits=traits)
    for n, npc in enumerate(village.behaviour.npcs):
        village.stay(npc, Goal(A.SQUARE, "square"))
        village.movement.place(npc, MapTile(map="high_street", x=52 + n, y=15))

    village.run(minutes=30)

    loner_rest = village.need("loner", Need.RELAXATION)
    assert loner_rest > 1.5 * village.need("mixer", Need.RELAXATION) > 0


def test_discipline_and_adventure_want_more_exercise() -> None:
    def exercise(**values: float) -> float:
        return rising(Need.EXERCISE, make_npc("x", "house_1", **values).values)

    assert exercise(discipline=0.9) > exercise() > exercise(discipline=0.1)
    assert exercise(adventure=0.9) > exercise()


def test_a_walk_round_lotus_lake_meets_exercise() -> None:
    lake = LOOPS["lychee_lane"]["lotus_lake"]
    config = STEADY.model_copy(
        update={"base": {A.EXERCISE: 10.0}, "loops": {"lychee_lane": {"lotus_lake": lake}}}
    )
    village = Village([ANA], config=config)
    village.behaviour.minds["ana"].needs[Need.EXERCISE] = 0.8

    village.run(minutes=20)

    tiles = [(m.x, m.y) for m in village.moves if m.entity == "ana" and m.map == "lychee_lane"]
    walked = sum(math.dist(a, b) for a, b in zip(tiles, tiles[1:], strict=False))
    passed = {tile for tile in lake if tile in tiles}
    assert village.behaviour.goal("ana") == Goal(A.EXERCISE, "lotus_lake")
    assert village.behaviour.minds["ana"].until is None
    assert walked > 300 and len(passed) == len(lake)
    assert village.need("ana", Need.EXERCISE) < 0.3


def test_every_loop_is_walkable() -> None:
    for map_id, named in DEFAULT_CONFIG.loops.items():
        town = MAPS[map_id]
        for loop, tiles in named.items():
            assert len(tiles) >= 2, loop
            assert all(town.walkable(x, y) for x, y in tiles), loop


def test_nobody_seeks_out_someone_out_for_a_walk() -> None:
    config = STEADY.model_copy(update={"base": {A.EXERCISE: 10.0}})
    village = Village([ANA, BEN], config=config)
    mind = village.behaviour.minds["ana"]

    village.run_until(lambda: mind.goal.activity is A.EXERCISE)

    assert not village.behaviour.available("ben", "ana")


def test_a_wander_keeps_walking_until_it_ends() -> None:
    config = STEADY.model_copy(update={"base": {A.WANDER: 10.0}, "dwell": {A.WANDER: (8, 8)}})
    village = Village([ANA], config=config)
    village.movement.place("ana", MapTile(map="high_street", x=51, y=15))
    mind = village.behaviour.minds["ana"]
    village.run_until(lambda: mind.goal.activity is A.WANDER and mind.ends is not None)
    since, stops = mind.since, set()

    while village.now < since + timedelta(minutes=7):
        village.world.loop.tick()
        stops.add(village.movement.position("ana"))

    assert mind.goal.activity is A.WANDER and mind.since == since
    assert len(stops) > 60


def test_a_bored_resident_moves_to_another_painting_before_leaving() -> None:
    village = Village([ANA], config=STEADY.model_copy(update={"switch": 100.0}))
    village.stay("ana", GALLERY, ago=20, left=20, boredom=0.6)
    village.movement.place("ana", MapTile(map="gallery_floor_0", x=4, y=2))
    first = village.movement.on_spot("ana")
    assert first is not None and first.kind is SpotKind.VIEWING

    village.run(minutes=DEFAULT_CONFIG.reconsider + 1)

    there = village.movement.on_spot("ana")
    assert there is not None and there.kind is SpotKind.VIEWING and there != first
    assert village.behaviour.goal("ana") == GALLERY
    assert village.need("ana", Need.BOREDOM) < 0.6 - DEFAULT_CONFIG.new_spot + 0.05


def test_making_something_still_lasts_its_whole_stay() -> None:
    writer = ANA.model_copy(update={"craft": Craft(medium=Medium.WRITING, form="poems")})
    village = Village([writer], config=STEADY)
    village.stay("ana", Goal(A.CREATE, "house_1"), left=40, inspiration=0.0)

    village.run(minutes=35)

    assert village.behaviour.goal("ana") == Goal(A.CREATE, "house_1")


def test_idle_is_short_and_only_a_fallback() -> None:
    neutral = {value: 0.5 for value in CoreValue}
    situation = Situation(neutral, CONTENT, 11.0, Point(51, 15, "high_street"), "house_1", 22.5)
    places = Places(with_every_location(MAPS))

    best = best_per_activity(scores(situation, places))

    assert min(best, key=lambda activity: best[activity][1]) is A.IDLE
    assert DEFAULT_CONFIG.dwell[A.IDLE][1] <= 3
