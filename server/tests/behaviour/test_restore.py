import math
from datetime import UTC, datetime, timedelta

from simile.behaviour import Activity, Behaviour, Goal, GoalChosen, Need
from simile.npc import load_npcs
from simile.sim import STEP, Clock, FakeWallClock, World
from simile.world import Movement
from simile.world.map import load_maps

MORNING = datetime(2026, 1, 1, 10, tzinfo=UTC)
LATER = MORNING + timedelta(days=2, hours=3)
OLD_NEEDS = {
    Need.SOCIAL: 0.3,
    Need.CURIOSITY: 0.6,
    Need.REST: 0.2,
    Need.NEWS: 0.4,
    Need.INSPIRATION: 0.5,
}
BEFORE_STAYS = {
    **OLD_NEEDS,
    Need.HUNGER: 0.45,
    Need.FINANCES: 0.0,
}
NEEDS = {**BEFORE_STAYS, Need.BOREDOM: 0.2, Need.RELAXATION: 0.4, Need.EXERCISE: 0.6}


class Village:
    def __init__(self) -> None:
        self.world = World(Clock(MORNING), FakeWallClock())
        self.movement = Movement(load_maps(), self.world.bus)
        self.behaviour = Behaviour(
            self.world.clock, self.world.bus, self.movement, load_npcs(), seed=0
        )
        self.goals: list[GoalChosen] = []
        self.world.bus.subscribe(GoalChosen, self.goals.append)
        self.world.loop.register(self.behaviour)
        self.world.loop.register(self.movement)
        self.behaviour.start()

    def think(self) -> None:
        for _ in range(round(self.behaviour.config.think_every / STEP)):
            self.world.loop.tick()


def test_restoring_puts_the_npc_back_to_what_they_were_doing() -> None:
    village = Village()
    behaviour = village.behaviour
    for mind in behaviour.minds.values():
        mind.until = MORNING
    village.think()
    walker = next(npc for npc, mind in behaviour.minds.items() if mind.walk is not None)
    village.world.clock.now = LATER
    village.goals.clear()

    behaviour.restore(
        walker,
        Goal(Activity.PARK, "park"),
        NEEDS,
        LATER - timedelta(minutes=20),
        LATER + timedelta(minutes=10),
        {"kofi": LATER + timedelta(minutes=30)},
    )

    mind = behaviour.minds[walker]
    assert (mind.goal, mind.since, mind.until) == (
        Goal(Activity.PARK, "park"),
        LATER - timedelta(minutes=20),
        LATER + timedelta(minutes=10),
    )
    assert mind.needs == NEEDS
    assert mind.cooldowns == {"kofi": LATER + timedelta(minutes=30)}
    assert mind.walk is None and not mind.paused
    assert village.goals == [GoalChosen(walker, "park", "park")]

    here = village.movement.position(walker)
    village.think()

    there = village.movement.position(walker)
    assert math.dist(here, there) < 1.5
    assert there == (round(there.x), round(there.y))
    assert behaviour.goal(walker) == Goal(Activity.PARK, "park")
    assert all(abs(behaviour.needs(walker)[need] - NEEDS[need]) < 0.01 for need in Need)


def test_someone_restored_without_an_until_decides_on_the_next_think() -> None:
    village = Village()
    village.world.clock.now = LATER
    behaviour = village.behaviour

    behaviour.restore("kofi", Goal(Activity.TALK, "henrietta"), NEEDS, LATER, None, {})
    village.goals.clear()
    village.think()

    assert "kofi" in {goal.npc for goal in village.goals}
    assert behaviour.goal("kofi").activity is not Activity.TALK


def test_a_save_from_before_hunger_keeps_its_start_value() -> None:
    village = Village()
    behaviour = village.behaviour
    started = behaviour.needs("kofi")
    village.world.clock.now = LATER

    behaviour.restore("kofi", Goal(Activity.PARK, "park"), OLD_NEEDS, LATER, None, {})

    needs = behaviour.needs("kofi")
    assert {need: needs[need] for need in OLD_NEEDS} == OLD_NEEDS
    low, high = behaviour.config.start_needs[Need.HUNGER]
    assert needs[Need.HUNGER] == started[Need.HUNGER] and low <= needs[Need.HUNGER] <= high


def test_a_save_from_before_boredom_relaxation_and_exercise_keeps_their_start_values() -> None:
    village = Village()
    behaviour = village.behaviour
    started = behaviour.needs("kofi")
    village.world.clock.now = LATER

    behaviour.restore("kofi", Goal(Activity.PARK, "park"), BEFORE_STAYS, LATER, None, {})

    needs = behaviour.needs("kofi")
    assert {need: needs[need] for need in BEFORE_STAYS} == BEFORE_STAYS
    for need in (Need.BOREDOM, Need.RELAXATION, Need.EXERCISE):
        low, high = behaviour.config.start_needs[need]
        assert needs[need] == started[need] and low <= needs[need] <= high
