import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from typer.testing import CliRunner

from simile.behaviour import (
    DEFAULT_CONFIG,
    Activity,
    Behaviour,
    BehaviourConfig,
    Goal,
    GoalChosen,
    MuralSpot,
    Need,
    Places,
)
from simile.behaviour.scoring import loops
from simile.behaviour.simulate import PLACES as SHARED
from simile.behaviour.simulate import simulate
from simile.cli import create_cli
from simile.npc import load_npcs
from simile.schema import (
    CoreValue,
    Craft,
    MapTile,
    Medium,
    Npc,
    Pay,
    PayKind,
    Pose,
    Shift,
    Weekday,
)
from simile.sim import STEP, Clock, EntityMoved, FakeWallClock, World
from simile.world import Movement, Point
from simile.world.map import STREET_DIR, SpotKind, load_maps, with_every_location
from simile.world.spots import purpose_of

STREETS = load_maps(STREET_DIR)
PLACES = Places(with_every_location(STREETS))
TEMPLATE = load_npcs()[0]
DAY = datetime(2026, 1, 1, tzinfo=UTC)
A = Activity
STEADY = DEFAULT_CONFIG.model_copy(update={"temperature": 0.0, "set_off_jitter": 0.0})


def keen(activity: Activity, **changes: object) -> BehaviourConfig:
    return STEADY.model_copy(update={"base": {activity: 10.0}, **changes})


def make_npc(id: str, home: str = "house_1", **changes: object) -> Npc:
    return TEMPLATE.model_copy(
        update={
            "id": id,
            "name": id.title(),
            "home": home,
            "values": dict.fromkeys(CoreValue, 0.5),
            "craft": None,
            "workplace": None,
            "shifts": [],
            "pay": None,
            **changes,
        }
    )


ANA = make_npc("ana")


class Village:
    """Behaviour and movement on the side-view maps."""

    def __init__(
        self, npcs: list[Npc], *, hour: float = 11, config: BehaviourConfig = STEADY
    ) -> None:
        self.world = World(Clock(DAY + timedelta(hours=hour)), FakeWallClock())
        self.movement = Movement(STREETS, self.world.bus)
        self.behaviour = Behaviour(
            self.world.clock, self.world.bus, self.movement, npcs, config=config, seed=0
        )
        self.moves: list[EntityMoved] = []
        self.world.bus.subscribe(EntityMoved, self.moves.append)
        self.world.bus.subscribe(
            GoalChosen, lambda e: self.movement.intend(e.npc, purpose_of(e.activity, e.target))
        )
        self.world.loop.register(self.behaviour)
        self.world.loop.register(self.movement)
        self.behaviour.start()

    @property
    def now(self) -> datetime:
        return self.world.clock.now

    def run(self, *, minutes: float) -> None:
        for _ in range(round(minutes * 60 / STEP)):
            self.world.loop.tick()

    def until(self, done: Callable[[], bool], *, minutes: float = 60) -> None:
        end = self.now + timedelta(minutes=minutes)
        while not done():
            assert self.now < end, "ran out of time"
            self.world.loop.tick()

    def arrived(self, npc: str, activity: Activity) -> Callable[[], bool]:
        mind = self.behaviour.minds[npc]
        return lambda: mind.goal.activity is activity and mind.walk is None

    def at(self, npc: str) -> Point:
        return self.movement.position(npc)

    def place_of(self, npc: str) -> str | None:
        location = PLACES.at(self.at(npc))
        return location.id if location else None

    def stops(self, npc: str) -> list[EntityMoved]:
        """Where they stood still, rather than mid-walk."""
        return [m for m in self.moves if m.entity == npc and m.pose is not Pose.WALKING]


def standing(move: EntityMoved) -> bool:
    return STREETS[move.map].standing(round(move.x), round(move.y))


def test_a_resident_at_home_is_inside_on_the_ground_floor() -> None:
    village = Village([ANA])

    here = village.at("ana")
    assert here.map == "house_1_floor_0"
    assert STREETS[here.map].standing(round(here.x), round(here.y))
    assert village.place_of("ana") == "house_1"


def test_residents_sleep_at_home() -> None:
    village = Village([ANA], hour=23.5)

    village.run(minutes=5)

    assert village.behaviour.goal("ana") == Goal(A.SLEEP, "house_1")
    assert village.at("ana").map == "house_1_floor_0"


def test_residents_go_to_work_upstairs_too() -> None:
    shifts = [Shift(days=list(Weekday), start=10, end=14)]
    pay = Pay(kind=PayKind.WAGE, amount=20)
    makers = [
        make_npc(f"npc{n}", f"house_{n % 10 + 1}", workplace="maker_space", shifts=shifts, pay=pay)
        for n in range(11)
    ]
    village = Village(makers, hour=9)

    village.until(lambda: all(village.arrived(n.id, A.WORK)() for n in makers), minutes=120)

    desks = [village.movement.on_spot(n.id) for n in makers]
    assert all(desk is not None and desk.kind is SpotKind.DESK for desk in desks)
    assert {village.place_of(n.id) for n in makers} == {"maker_space"}
    assert any(village.at(n.id).map != "maker_space_floor_0" for n in makers)


def test_hungry_residents_eat() -> None:
    village = Village([ANA], config=keen(A.NOODLE_BAR))
    village.behaviour.minds["ana"].needs[Need.HUNGER] = 0.85

    village.until(village.arrived("ana", A.NOODLE_BAR))
    village.run(minutes=15)

    seat = village.movement.on_spot("ana")
    assert village.place_of("ana") == "noodle_bar"
    assert seat is not None and seat.kind is SpotKind.SEAT
    assert village.behaviour.needs("ana")[Need.HUNGER] < 0.6


def test_residents_visit_the_gallery() -> None:
    village = Village([ANA], config=keen(A.GALLERY))

    village.until(village.arrived("ana", A.GALLERY))

    spot = village.movement.on_spot("ana")
    assert village.place_of("ana") == "gallery"
    assert spot is not None and spot.kind is SpotKind.VIEWING


def test_drinkers_take_spots_downstairs_then_climb_to_the_tables() -> None:
    drinkers = [make_npc(f"npc{n}", f"house_{n + 1}") for n in range(8)]
    village = Village(drinkers, config=keen(A.COFFEE_SHOP))

    village.until(lambda: all(village.arrived(n.id, A.COFFEE_SHOP)() for n in drinkers))

    spots = {n.id: village.movement.on_spot(n.id) for n in drinkers}
    on = {npc: spot.map for npc, spot in spots.items() if spot is not None}
    upstairs = [npc for npc, map_id in on.items() if map_id == "coffee_shop_floor_1"]
    assert len(on) == len(drinkers)
    assert set(on.values()) == {"coffee_shop_floor_0", "coffee_shop_floor_1"}
    assert {village.place_of(n.id) for n in drinkers} == {"coffee_shop"}
    for npc in upstairs:
        maps = [m.map for m in village.moves if m.entity == npc]
        assert maps.index("coffee_shop_floor_0") < maps.index("coffee_shop_floor_1")


def test_a_bored_resident_moves_to_a_painting_upstairs_when_downstairs_is_taken() -> None:
    village = Village([ANA], config=STEADY.model_copy(update={"switch": 100.0}))
    village.movement.place("ana", MapTile(map="gallery_floor_0", x=4, y=2))
    for n, x in enumerate((5, 7, 8, 10, 11)):
        village.movement.place(f"visitor{n}", MapTile(map="gallery_floor_0", x=x, y=2))
    needs = dict.fromkeys(Need, 0.0) | {Need.BOREDOM: 0.6}
    since, until = village.now - timedelta(minutes=20), village.now + timedelta(minutes=20)
    village.behaviour.restore("ana", Goal(A.GALLERY, "gallery"), needs, since, until, {})

    village.moves.clear()

    village.run(minutes=DEFAULT_CONFIG.reconsider + 1)

    looked = [m.map for m in village.moves if m.entity == "ana" and m.pose is Pose.LOOKING]
    assert village.behaviour.goal("ana") == Goal(A.GALLERY, "gallery")
    assert looked and looked[0] in ("gallery_floor_1", "gallery_floor_2")


def test_a_wander_on_the_high_street_stays_on_it() -> None:
    config = keen(A.WANDER, dwell={A.WANDER: (30, 30)})
    village = Village([ANA], config=config)
    village.movement.place("ana", MapTile(map="high_street", x=70, y=15))
    village.behaviour.restore("ana", Goal(A.IDLE), {}, village.now, village.now, {})
    village.moves.clear()

    village.run(minutes=25)

    stops = village.stops("ana")
    reach = DEFAULT_CONFIG.wander_radius
    assert len(stops) > 5
    assert {stop.map for stop in stops} == {"high_street"}
    assert all(standing(stop) for stop in stops)
    assert all(abs(b.x - a.x) <= reach for a, b in zip(stops, stops[1:], strict=False))


def test_a_wander_never_stops_partway_up_a_ladder() -> None:
    config = keen(A.WANDER, dwell={A.WANDER: (60, 60)}, wander_radius=6)
    village = Village([ANA], config=config)
    village.movement.place("ana", MapTile(map="lychee_lane", x=45, y=15))
    village.behaviour.restore("ana", Goal(A.IDLE), {}, village.now, village.now, {})
    village.moves.clear()

    village.run(minutes=55)

    stops = village.stops("ana")
    passed = {(round(m.x), round(m.y)) for m in village.moves if m.entity == "ana"}
    assert len(stops) > 10
    assert all(stop.map == "lychee_lane" and standing(stop) for stop in stops)
    assert {(45, 13), (47, 12)} <= passed


def test_a_wander_from_upstairs_starts_outside_the_front_door() -> None:
    village = Village([ANA], config=keen(A.WANDER))
    village.movement.place("ana", MapTile(map="house_1_floor_1", x=3, y=2))
    village.behaviour.restore("ana", Goal(A.IDLE), {}, village.now, village.now, {})

    village.until(lambda: village.behaviour.minds["ana"].walk is not None)

    destination = village.behaviour.minds["ana"].walk.destination
    assert destination is not None and destination.map == "lychee_lane"
    assert abs(destination.x - 7) <= DEFAULT_CONFIG.wander_radius


def test_the_exercise_walks_are_on_the_streets_and_climb_to_the_lookout() -> None:
    walks = loops(PLACES)
    config = keen(A.EXERCISE, loops_on={"lychee_lane": STEADY.loops_on["lychee_lane"]})
    village = Village([ANA], config=config)
    village.behaviour.minds["ana"].needs[Need.EXERCISE] = 0.8

    village.run(minutes=20)

    passed = {(m.map, round(m.x), round(m.y)) for m in village.moves if m.entity == "ana"}
    assert set(walks) == set(DEFAULT_CONFIG.loops)
    assert all(STREETS[p.map].standing(round(p.x), round(p.y)) for w in walks.values() for p in w)
    assert village.behaviour.goal("ana") == Goal(A.EXERCISE, "lotus_lake")
    assert {(p.map, round(p.x), round(p.y)) for p in walks["lotus_lake"]} <= passed


def test_a_muralist_walks_to_their_wall_on_its_own_street() -> None:
    muralist = make_npc("ana", craft=Craft(medium=Medium.MURAL, form="murals"))
    village = Village([muralist], config=keen(A.CREATE))
    wall = MuralSpot("daily_grind", MapTile(map="high_street", x=28, y=15))
    village.behaviour.hooks.set(mural_wall=lambda npc: wall)
    village.behaviour.minds["ana"].needs[Need.INSPIRATION] = 0.8

    village.until(village.arrived("ana", A.CREATE), minutes=90)

    assert village.at("ana") == Point(28, 15, "high_street")


def test_a_place_counts_every_floor_of_its_building() -> None:
    assert PLACES.at(Point(5, 2, "coffee_shop_floor_1")) == PLACES.location("coffee_shop")
    assert PLACES.at(Point(3, 2, "house_4_floor_1")) == PLACES.location("house_4")
    assert PLACES.at(Point(40, 15, "high_street")) == PLACES.location("cafe_terrace")
    assert PLACES.at(Point(20, 15, "kapok_walk")) is None


def test_a_day_on_the_side_view_maps_spends_time_where_todays_does() -> None:
    start = DAY + timedelta(hours=8)

    observer, _ = asyncio.run(simulate(4, start=start, maps=STREET_DIR))

    awake = sum(observer.awake_at.values())
    shares = {place: observer.awake_at[place] / awake for place in SHARED}
    assert sum(observer.out.values()) > 0
    assert 0.2 < shares["home"] < 0.6
    assert shares["coffee_shop"] > 0.05
    assert sum(share > 0 for share in shares.values()) >= 7


def test_simulate_runs_on_the_maps_given() -> None:
    args = ["behaviour", "simulate", "--hours", "1", "--start", "11", "--maps", str(STREET_DIR)]

    result = CliRunner().invoke(create_cli(), args)

    assert result.exit_code == 0, result.output
    assert "**Time by place.**" in result.output
