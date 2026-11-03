import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

from simile.behaviour import Activity, Behaviour, Goal
from simile.npc import load_npcs
from simile.persistence import SavedWorld, restore
from simile.schema import Npc, Pose, Tile
from simile.sim import Clock, FakeWallClock, World
from simile.world import Movement
from simile.world.map import SpotKind, load_maps, with_every_location
from simile.world.movement import inside

MAPS = load_maps()
TOWN = with_every_location(MAPS)
NPCS = load_npcs()
SAVE = SavedWorld.model_validate_json(
    (Path(__file__).parent / "save_asleep_downstairs.json").read_text()
)
DOWNSTAIRS = ("desmond", "henrietta", "kofi")


class Village:
    def __init__(self, npcs: list[Npc] = NPCS) -> None:
        self.world = World(Clock(datetime(2026, 1, 1, 10, tzinfo=UTC)), FakeWallClock())
        self.movement = Movement(MAPS, self.world.bus)
        self.behaviour = Behaviour(self.world.clock, self.world.bus, self.movement, npcs, seed=0)
        self.world.loop.register(self.behaviour)
        self.world.loop.register(self.movement)
        self.behaviour.start()

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

    village.run(min(s.until for s in SAVE.npcs.values()) - village.world.clock.now)
    assert all(village.in_bed(npc) for npc in SAVE.npcs)


def test_a_resident_saved_in_bed_loads_lying_down() -> None:
    village = Village()

    restore(SAVE, village.behaviour)

    assert village.behaviour.minds["marguerite"].walk is None
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
