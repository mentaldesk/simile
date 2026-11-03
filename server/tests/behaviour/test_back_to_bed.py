import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

from simile.behaviour import Activity, Behaviour, Goal, GoalChosen
from simile.npc import load_npcs
from simile.persistence import SavedWorld, restore
from simile.schema import Npc, Pose, Tile
from simile.sim import Clock, FakeWallClock, World
from simile.world import Movement, Point
from simile.world.map import SpotKind, load_maps, with_every_location
from simile.world.movement import inside

MAPS = load_maps()
TOWN = with_every_location(MAPS)
NPCS = load_npcs()
SAVE = SavedWorld.model_validate_json(
    (Path(__file__).parent / "save_asleep_downstairs.json").read_text()
)
DOWNSTAIRS = ("desmond", "henrietta", "kofi")
MORNING = datetime(2026, 1, 1, 10, tzinfo=UTC)


class Village:
    def __init__(self, npcs: list[Npc] = NPCS, start: datetime = MORNING) -> None:
        self.world = World(Clock(start), FakeWallClock())
        self.movement = Movement(MAPS, self.world.bus)
        self.behaviour = Behaviour(self.world.clock, self.world.bus, self.movement, npcs, seed=0)
        self.world.loop.register(self.behaviour)
        self.world.loop.register(self.movement)
        self.woke: dict[str, datetime] = {}
        self.world.bus.subscribe(GoalChosen, self._on_goal)
        self.behaviour.start()

    def _on_goal(self, event: GoalChosen) -> None:
        if event.activity != Activity.SLEEP.value:
            self.woke.setdefault(event.npc, self.world.clock.now)

    def run(self, duration: timedelta) -> None:
        asyncio.run(self.world.loop.run(duration))

    def in_bed(self, npc: str) -> bool:
        spot = self.movement.on_spot(npc)
        home = TOWN.location(self.behaviour.npcs[npc].home)
        return (
            spot is not None
            and spot.kind is SpotKind.BED
            and inside(home, self.movement.position(npc))
            and self.movement.posture(npc)[0] is Pose.SLEEPING
        )


def test_residents_asleep_downstairs_when_a_save_loads_go_up_to_bed() -> None:
    village = Village()
    behaviour = village.behaviour

    restore(SAVE, behaviour)

    assert all(behaviour.minds[npc].walk is not None for npc in DOWNSTAIRS)
    village.run(timedelta(minutes=10))
    for npc, saved in SAVE.npcs.items():
        mind = behaviour.minds[npc]
        assert village.in_bed(npc), npc
        assert (mind.goal, mind.until) == (Goal(Activity.SLEEP, saved.target), saved.until)

    village.woke.clear()
    for npc, saved in sorted(SAVE.npcs.items(), key=lambda item: item[1].until):
        village.run(saved.until - timedelta(minutes=1) - village.world.clock.now)
        assert village.in_bed(npc) and npc not in village.woke, npc
    village.run(timedelta(minutes=10))
    assert all(village.woke[npc] >= saved.until for npc, saved in SAVE.npcs.items())


def test_a_fresh_start_at_night_puts_residents_in_bed() -> None:
    village = Village(start=datetime(2026, 1, 3, 2, 45, tzinfo=UTC))

    village.run(timedelta(minutes=10))

    assert all(village.in_bed(npc.id) for npc in NPCS)


def test_a_resident_saved_in_bed_loads_lying_down() -> None:
    village = Village()

    restore(SAVE, village.behaviour)

    assert village.movement.position("marguerite") == Point(3, 2, "house_1_floor_1")
    assert village.in_bed("marguerite")


def test_a_resident_saved_on_their_way_to_bed_goes_to_it() -> None:
    village = Village()
    behaviour = village.behaviour
    square = TOWN.location("square")
    on_the_way = SAVE.npcs["kofi"].model_copy(
        update={
            "position": Tile(x=square.entry.x, y=square.entry.y),
            "map": square.map,
            "until": None,
        }
    )

    restore(SAVE.model_copy(update={"npcs": {"kofi": on_the_way}}), behaviour)
    village.run(timedelta(minutes=30))

    mind = behaviour.minds["kofi"]
    assert village.in_bed("kofi")
    assert mind.goal == Goal(Activity.SLEEP, "house_6")
    assert mind.until is not None and mind.until > village.world.clock.now + timedelta(hours=3)


def test_a_resident_with_no_bed_at_home_sleeps_where_they_are() -> None:
    npc = NPCS[0].model_copy(update={"id": "nomad", "home": "gallery", "workplace": None})
    village = Village([npc])
    gallery = TOWN.location("gallery")
    asleep = SAVE.npcs["kofi"].model_copy(
        update={
            "position": Tile(x=gallery.entry.x, y=gallery.entry.y),
            "map": gallery.map,
            "target": "gallery",
        }
    )

    restore(SAVE.model_copy(update={"npcs": {"nomad": asleep}}), village.behaviour)
    here = village.movement.position("nomad")
    village.run(timedelta(minutes=10))

    assert village.behaviour.minds["nomad"].walk is None
    assert village.movement.position("nomad") == here
    assert village.movement.posture("nomad")[0] is Pose.STANDING
