from datetime import UTC, datetime, timedelta

from simile.behaviour import DEFAULT_CONFIG, Activity, Behaviour, Goal, GoalChosen
from simile.npc import load_npcs
from simile.schema import CoreValue, MapTile, Npc
from simile.sim import STEP, Clock, FakeWallClock, World
from simile.world import Movement, Point
from simile.world.map import load_maps

MAPS = load_maps()
MORNING = datetime(2026, 1, 1, 8, tzinfo=UTC)
TEMPLATE = load_npcs()[0]
SPOT = MapTile(map="coffee_shop", x=5, y=4)
WORK = Goal(Activity.COFFEE_SHOP, "coffee_shop")


NO_WORK = {"workplace": None, "shifts": [], "pay": None}


def make_npc(id: str, home: str) -> Npc:
    scores = dict.fromkeys(CoreValue, 0.5)
    return TEMPLATE.model_copy(
        update={
            "id": id,
            "name": id.title(),
            "home": home,
            "values": scores,
            "craft": None,
            **NO_WORK,
        }
    )


class Village:
    def __init__(self, start: datetime = MORNING) -> None:
        self.world = World(Clock(start), FakeWallClock())
        self.movement = Movement(MAPS, self.world.bus)
        npcs = [make_npc("ana", "house_1"), make_npc("ben", "house_2")]
        self.behaviour = Behaviour(
            self.world.clock, self.world.bus, self.movement, npcs, config=DEFAULT_CONFIG, seed=0
        )
        self.goals: list[GoalChosen] = []
        self.world.bus.subscribe(GoalChosen, self.goals.append)
        self.world.loop.register(self.behaviour)
        self.world.loop.register(self.movement)
        self.behaviour.start()

    def run(self, *, minutes: float) -> None:
        for _ in range(round(minutes * 60 / STEP)):
            self.world.loop.tick()

    def at_spot(self, npc: str) -> bool:
        return self.movement.position(npc) == Point(SPOT.x, SPOT.y, SPOT.map)


def test_a_held_resident_walks_to_the_spot_and_stays_there_without_deciding() -> None:
    village = Village()

    village.behaviour.hold("ana", SPOT, WORK)
    village.run(minutes=180)

    assert village.at_spot("ana")
    assert village.behaviour.goal("ana") == WORK
    assert [goal for goal in village.goals if goal.npc == "ana"][-1:] == [
        GoalChosen("ana", "coffee_shop", "coffee_shop")
    ]


def test_a_held_resident_cant_be_sought_or_nudged() -> None:
    village = Village()
    village.behaviour.hold("ana", SPOT, WORK)

    assert not village.behaviour.available("ben", "ana")
    assert not village.behaviour.nudge("ana", Goal(Activity.PARK, "park"), 1.0)
    assert village.behaviour.goal("ana") == WORK


def test_a_held_resident_stays_up_past_their_bedtime() -> None:
    village = Village(start=MORNING.replace(hour=20))
    village.behaviour.hold("ana", SPOT, WORK)

    village.run(minutes=5 * 60)

    assert village.behaviour.goal("ana") == WORK
    assert village.at_spot("ana")


def test_a_held_resident_goes_back_to_the_spot_after_a_talk() -> None:
    village = Village()
    village.behaviour.hold("ana", SPOT, WORK)
    village.run(minutes=1)

    village.behaviour.pause("ana", "ben")
    assert village.behaviour.goal("ana") == Goal(Activity.TALK, "ben")
    village.movement.place("ana", MapTile(map="coffee_shop", x=12, y=9))
    village.behaviour.resume("ana")
    village.run(minutes=1)

    assert village.behaviour.goal("ana") == WORK
    assert village.at_spot("ana")


def test_a_released_resident_decides_on_the_next_think() -> None:
    village = Village()
    village.behaviour.hold("ana", SPOT, WORK)
    village.run(minutes=1)
    village.goals.clear()

    village.behaviour.release("ana")
    village.run(minutes=0.1)

    assert "ana" in {goal.npc for goal in village.goals}
    assert village.behaviour.available("ben", "ana") or village.behaviour.at_home("ana")


def test_a_resident_released_to_stay_stays_put_for_that_long() -> None:
    village = Village()
    village.behaviour.hold("ana", SPOT, WORK)
    village.run(minutes=1)

    released = village.world.clock.now
    village.behaviour.release("ana", stay=timedelta(minutes=20))
    village.run(minutes=19)
    assert village.behaviour.goal("ana") == WORK
    assert village.behaviour.minds["ana"].since < released
    assert village.at_spot("ana")
    assert village.behaviour.available("ben", "ana")

    village.run(minutes=2)
    assert village.behaviour.minds["ana"].since > released + timedelta(minutes=19)


def test_releasing_someone_not_held_changes_nothing() -> None:
    village = Village()
    before = village.behaviour.goal("ana")

    village.behaviour.release("ana")

    assert village.behaviour.goal("ana") == before
    assert village.behaviour.minds["ana"].until is not None
