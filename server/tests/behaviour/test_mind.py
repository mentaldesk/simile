import json
import logging
import math
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from simile.behaviour import (
    DEFAULT_CONFIG,
    Activity,
    Behaviour,
    BehaviourConfig,
    Goal,
    GoalChosen,
    MuralSpot,
    Need,
)
from simile.npc import load_npcs
from simile.schema import (
    PLAYER_ID,
    VILLAGE_MAP,
    Baseline,
    CoreValue,
    Craft,
    Intention,
    MapTile,
    Medium,
    Npc,
    Relationship,
    Tile,
)
from simile.sim import STEP, Clock, EntityMoved, FakeWallClock, World
from simile.world import Movement, Outcome, Point
from simile.world.map import WALKING_SPEED, load_maps, with_every_location
from simile.world.movement import inside

MAPS = load_maps()
TOWN = with_every_location(MAPS)
MORNING = datetime(2026, 1, 1, 8, tzinfo=UTC)
TEMPLATE = load_npcs()[0]
A = Activity


NO_WORK = {"workplace": None, "shifts": [], "pay": None}


def make_npc(id: str, home: str, **values: float) -> Npc:
    """An NPC who cares about everything at 0.5, except the values given."""
    scores = {value: values.get(value.value, 0.5) for value in CoreValue}
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


ANA = make_npc("ana", "house_1")
BEN = make_npc("ben", "house_2")
CAL = make_npc("cal", "house_3")


def keen(activity: Activity, **changes: object) -> BehaviourConfig:
    """Everyone always picks `activity` when awake."""
    return DEFAULT_CONFIG.model_copy(
        update={"base": {activity: 10.0}, "temperature": 0.0, **changes}
    )


class Store:
    def __init__(self, *relationships: Relationship) -> None:
        self.known = list(relationships)

    def relationships(self, owner: str) -> list[Relationship]:
        return [rel for rel in self.known if rel.owner == owner]


class Village:
    def __init__(
        self,
        npcs: list[Npc],
        *,
        start: datetime = MORNING,
        seed: int = 0,
        config: BehaviourConfig = DEFAULT_CONFIG,
        store: Store | None = None,
        placed: dict[str, str | MapTile] | None = None,
    ) -> None:
        self.world = World(Clock(start), FakeWallClock())
        self.movement = Movement(MAPS, self.world.bus)
        self.behaviour = Behaviour(
            self.world.clock, self.world.bus, self.movement, npcs, store, config=config, seed=seed
        )
        self.goals: list[tuple[datetime, GoalChosen]] = []
        self.world.bus.subscribe(GoalChosen, lambda e: self.goals.append((self.clock.now, e)))
        self.world.loop.register(self.behaviour)
        self.world.loop.register(self.movement)
        for entity, place in (placed or {}).items():
            self.movement.place(entity, place)
        self.behaviour.start()

    @property
    def clock(self) -> Clock:
        return self.world.clock

    def run(self, *, hours: float = 0, minutes: float = 0) -> None:
        for _ in range(round((hours * 3600 + minutes * 60) / STEP)):
            self.world.loop.tick()

    def run_until(self, done: Callable[[], bool], *, minutes: float = 120) -> None:
        end = self.clock.now.timestamp() + minutes * 60
        while not done():
            assert self.clock.now.timestamp() < end, "ran out of time"
            self.world.loop.tick()

    def at_home(self, npc: Npc) -> bool:
        x, y = self.movement.position(npc.id)
        return inside(TOWN.location(npc.home), (round(x), round(y)))

    def chosen(self, npc: str) -> list[str]:
        return [str(Goal(A(e.activity), e.target)) for _, e in self.goals if e.npc == npc]


def at(hour: float) -> datetime:
    return datetime(2026, 1, 1, tzinfo=UTC).replace(hour=int(hour), minute=round(hour % 1 * 60))


def test_starts_everyone_at_home_with_a_goal() -> None:
    village = Village([ANA, BEN, CAL])

    assert all(village.at_home(npc) for npc in (ANA, BEN, CAL))
    assert [e.npc for _, e in village.goals] == ["ana", "ben", "cal"]
    assert all(village.behaviour.goal(npc.id).target == npc.home for npc in (ANA, BEN, CAL))


def test_leaves_home_for_their_goal_and_stays_a_while() -> None:
    village = Village([ANA], config=keen(A.COFFEE_SHOP))

    village.run_until(lambda: village.behaviour.goal("ana").activity is A.COFFEE_SHOP)
    village.run_until(lambda: not village.behaviour.minds["ana"].walk)
    arrived = village.movement.position("ana")
    village.run(minutes=10)

    assert inside(TOWN.location("coffee_shop"), (round(arrived.x), round(arrived.y)))
    assert village.movement.position("ana") == arrived


def test_decides_again_when_they_have_been_somewhere_long_enough() -> None:
    village = Village([ANA], seed=3)

    village.run(hours=3)

    assert len(village.chosen("ana")) > 3


def test_everyone_heads_home_at_bedtime_and_is_there_at_three_am() -> None:
    npcs = [make_npc(f"npc_{i}", f"house_{i}", adventure=0.95, pleasure=0.95) for i in (1, 4, 9)]
    placed = {npc.id: "square" for npc in npcs}
    village = Village(npcs, start=at(20), placed=placed, config=keen(A.SQUARE))

    village.run(hours=7)

    assert village.clock.now == at(3).replace(day=2)
    assert all(village.at_home(npc) for npc in npcs)
    assert all(village.behaviour.goal(npc.id).activity is A.SLEEP for npc in npcs)


def test_nobody_gets_up_before_they_wake() -> None:
    early = make_npc("early", "house_1", discipline=0.95)
    late = make_npc("late", "house_2", pleasure=0.95, discipline=0.05)
    village = Village([early, late], start=at(3), config=keen(A.SQUARE))

    village.run(hours=7)

    got_up = {
        npc: min(when for when, e in village.goals if e.npc == npc and e.activity == A.SQUARE)
        for npc in ("early", "late")
    }
    for npc, when in got_up.items():
        assert hours(when) >= village.behaviour.minds[npc].wake
    assert got_up["early"] < got_up["late"]


def hours(when: datetime) -> float:
    return when.hour + when.minute / 60 + when.second / 3600


def test_needs_rise_over_time() -> None:
    config = DEFAULT_CONFIG.model_copy(update={"start_dwell": (120, 120)})
    village = Village([ANA], config=config)
    before = village.behaviour.needs("ana")

    village.run(hours=1)
    after = village.behaviour.needs("ana")

    assert after[Need.SOCIAL] > before[Need.SOCIAL]
    assert after[Need.CURIOSITY] > before[Need.CURIOSITY]


def test_connection_makes_them_lonely_faster() -> None:
    config = DEFAULT_CONFIG.model_copy(update={"start_dwell": (120, 120)})
    keen, aloof = (
        make_npc("keen", "house_1", connection=0.9),
        make_npc("aloof", "house_2", connection=0.1),
    )
    village = Village([keen, aloof], config=config)
    for mind in village.behaviour.minds.values():
        mind.needs[Need.SOCIAL] = 0.2

    village.run(hours=1)

    lonelier = {npc: village.behaviour.needs(npc)[Need.SOCIAL] - 0.2 for npc in ("keen", "aloof")}
    assert lonelier["keen"] > 3 * lonelier["aloof"] > 0


def test_knowledge_and_open_mindedness_make_them_want_the_news() -> None:
    config = DEFAULT_CONFIG.model_copy(update={"start_dwell": (120, 120)})
    reader = make_npc("reader", "house_1", knowledge=0.9, open_mindedness=0.8)
    incurious = make_npc("incurious", "house_2", knowledge=0.1, open_mindedness=0.2)
    village = Village([reader, incurious], config=config)
    for mind in village.behaviour.minds.values():
        mind.needs[Need.NEWS] = 0.3

    village.run(hours=1)

    assert village.behaviour.needs("reader")[Need.NEWS] > 0.5
    assert village.behaviour.needs("incurious")[Need.NEWS] < 0.3


def test_resting_at_home_brings_tiredness_down() -> None:
    config = DEFAULT_CONFIG.model_copy(update={"start_dwell": (120, 120)})
    village = Village([ANA], config=config)
    village.behaviour.minds["ana"].needs[Need.REST] = 0.8

    village.run(hours=1)

    assert village.behaviour.needs("ana")[Need.REST] < 0.8


def test_pause_stops_them_and_their_decisions_until_resumed() -> None:
    village = Village([ANA], config=keen(A.PARK))
    village.run_until(lambda: village.behaviour.minds["ana"].walk is not None)

    village.behaviour.pause("ana", "ben")
    village.run(minutes=1)
    stopped = village.movement.position("ana")
    village.run(hours=2)

    assert village.behaviour.goal("ana") == Goal(A.TALK, "ben")
    assert village.movement.position("ana") == stopped
    assert village.behaviour.state("ana")["paused"] is True

    village.behaviour.resume("ana")
    village.run(minutes=1)

    assert village.behaviour.goal("ana") == Goal(A.PARK, "park")
    assert village.behaviour.minds["ana"].paused is False


def test_pause_and_resume_ignore_the_player() -> None:
    village = Village([ANA])

    village.behaviour.pause(PLAYER_ID, "ana")
    village.behaviour.resume(PLAYER_ID)


def test_talking_meets_social_need() -> None:
    village = Village([ANA])
    village.behaviour.pause("ana", "ben")
    village.behaviour.minds["ana"].needs[Need.SOCIAL] = 0.9

    village.run(minutes=30)

    assert village.behaviour.needs("ana")[Need.SOCIAL] < 0.5


def test_talking_with_the_player_meets_less_social_need_than_talking_with_a_resident() -> None:
    steady = DEFAULT_CONFIG.model_copy(
        update={
            "rise": {**DEFAULT_CONFIG.rise, Need.SOCIAL: 0.0},
            "rise_values": {**DEFAULT_CONFIG.rise_values, Need.SOCIAL: {}},
            "company": 0.0,
        }
    )
    village = Village([ANA, BEN], config=steady)
    village.behaviour.pause("ana", "cal")
    village.behaviour.pause("ben", PLAYER_ID)
    for npc in ("ana", "ben"):
        village.behaviour.minds[npc].needs[Need.SOCIAL] = 0.9

    village.run(minutes=5)

    talk = steady.effects[A.TALK][Need.SOCIAL] * 5 / 60
    assert village.behaviour.needs("ana")[Need.SOCIAL] == pytest.approx(0.9 + talk)
    assert village.behaviour.needs("ben")[Need.SOCIAL] == pytest.approx(
        0.9 + talk * steady.player_relief
    )
    assert steady.player_relief == 0.5


def test_a_nudge_tips_their_next_decision_and_only_that_one() -> None:
    village = Village(
        [ANA, BEN],
        start=at(11),
        config=DEFAULT_CONFIG.model_copy(update={"temperature": 0.0}),
        placed={"ana": "square", "ben": "square"},
    )
    now = village.clock.now
    needs = village.behaviour.needs("ana")
    staying = Goal(A.SQUARE, "square")
    for npc in ("ana", "ben"):
        village.behaviour.restore(npc, staying, needs, now, now + timedelta(hours=1), {})

    assert village.behaviour.nudge("ana", Goal(A.SEEK, "ben"), 5.0)
    village.run(minutes=0.1)

    assert village.behaviour.goal("ana") == Goal(A.SEEK, "ben")
    assert village.behaviour.minds["ana"].options["seek ben"] > 5.0
    assert village.behaviour.minds["ana"].nudge is None
    assert village.behaviour.goal("ben") == staying


def test_a_nudge_stops_a_walk_and_waits_for_anyone_talking_or_asleep() -> None:
    village = Village([ANA, BEN], start=at(11), config=keen(A.PARK), placed={"ben": "square"})
    village.run_until(lambda: village.behaviour.minds["ana"].walk is not None)

    assert village.behaviour.nudge("ana", Goal(A.SEEK, "ben"), 50.0)
    assert village.behaviour.minds["ana"].walk is None
    village.run(minutes=0.1)
    assert village.behaviour.goal("ana") == Goal(A.SEEK, "ben")

    village.behaviour.pause("ben", "cal")
    assert not village.behaviour.nudge("ben", Goal(A.SEEK, "ana"), 50.0)
    assert village.behaviour.minds["ben"].nudge is None

    night = Village([ANA], start=at(23.5))
    assert not night.behaviour.nudge("ana", Goal(A.PARK, "park"), 50.0)


def test_a_nudge_left_at_bedtime_is_dropped_with_the_new_goal() -> None:
    village = Village([ANA], start=datetime(2026, 1, 1, 22, 29, 58, tzinfo=UTC))
    assert village.behaviour.minds["ana"].bedtime == 22.5

    assert village.behaviour.nudge("ana", Goal(A.PARK, "park"), 50.0)
    village.run(minutes=0.2)

    assert village.behaviour.goal("ana").activity is A.SLEEP
    assert village.behaviour.minds["ana"].nudge is None


def test_seekers_ask_to_talk_and_both_pause_when_accepted() -> None:
    requests: list[tuple[str, str]] = []
    village = Village(
        [ANA, BEN], start=at(11), config=keen(A.SEEK), placed={"ana": "square", "ben": "park"}
    )

    def accept(a: str, b: str) -> bool:
        requests.append((a, b))
        return True

    village.behaviour.hooks.set(request_conversation=accept)
    village.run_until(lambda: bool(requests))
    village.run(minutes=5)

    assert len(requests) == 1
    a, b = requests[0]
    assert village.behaviour.goal(a) == Goal(A.TALK, b)
    assert village.behaviour.goal(b) == Goal(A.TALK, a)
    assert village.movement.distance(a, b) <= DEFAULT_CONFIG.talk_range


def test_seekers_hang_around_when_declined_and_do_not_ask_again_soon() -> None:
    requests: list[tuple[str, str]] = []
    config = keen(A.SEEK, seek_cooldown=45)
    village = Village([ANA, BEN], start=at(11), config=config, placed={"ben": "park"})

    def decline(a: str, b: str) -> bool:
        requests.append((a, b))
        return False

    village.behaviour.hooks.set(request_conversation=decline)
    village.run(minutes=40)

    assert requests.count(("ana", "ben")) == 1
    assert village.behaviour.minds["ana"].cooldowns["ben"] > village.clock.now


def test_seekers_can_seek_the_player() -> None:
    requests: list[tuple[str, str]] = []
    village = Village([ANA], start=at(11), config=keen(A.SEEK))
    village.movement.place(PLAYER_ID, "square")

    def decline(a: str, b: str) -> bool:
        requests.append((a, b))
        return False

    village.behaviour.hooks.set(request_conversation=decline)
    village.run_until(lambda: bool(requests))

    assert requests == [("ana", PLAYER_ID)]


def test_seekers_follow_someone_through_a_door() -> None:
    requests: list[tuple[str, str]] = []
    village = Village([ANA], start=at(11), config=keen(A.SEEK))
    village.movement.place(PLAYER_ID, MapTile(map="coffee_shop", x=5, y=6))

    def decline(a: str, b: str) -> bool:
        requests.append((a, b))
        return False

    village.behaviour.hooks.set(request_conversation=decline)
    village.run_until(lambda: bool(requests))

    assert requests == [("ana", PLAYER_ID)]
    assert village.movement.position("ana").map == "coffee_shop"


def test_npcs_who_leave_the_player_alone_dont_seek_them_until_let_go() -> None:
    requests: list[tuple[str, str]] = []
    village = Village([ANA], start=at(11), config=keen(A.SEEK))
    village.movement.place(PLAYER_ID, "square")
    village.behaviour.leave_player_alone.add("ana")

    def decline(a: str, b: str) -> bool:
        requests.append((a, b))
        return False

    village.behaviour.hooks.set(request_conversation=decline)
    village.run(minutes=30)
    assert len(village.chosen("ana")) > 1
    assert f"seek {PLAYER_ID}" not in village.chosen("ana")

    village.behaviour.leave_player_alone.discard("ana")
    village.run_until(lambda: bool(requests))
    assert requests == [("ana", PLAYER_ID)]


def test_seekers_choose_friends_from_their_relationships() -> None:
    baseline = Baseline(like=0.5, trust=0.5, respect=0.5)
    friend = Relationship(
        owner="ana",
        about="cal",
        like=0.95,
        trust=0.9,
        respect=0.8,
        familiarity=0.9,
        baseline=baseline,
        last_interaction=at(10),
    )
    ana = make_npc("ana", "house_1", connection=0.95)
    village = Village(
        [ana, BEN, CAL],
        start=at(11),
        config=DEFAULT_CONFIG.model_copy(update={"temperature": 0.0}),
        store=Store(friend),
        placed={"ana": "square", "ben": "square", "cal": "park"},
    )

    assert village.behaviour.goal("ana") == Goal(A.SEEK, "cal")


def test_reads_the_news_at_a_terminal() -> None:
    readers: list[str] = []
    village = Village([ANA], config=keen(A.NEWS))
    village.behaviour.hooks.set(
        read_news=lambda npc: readers.append(npc.id), news_interest=lambda npc: 1.0
    )

    village.run_until(lambda: bool(readers))

    location = village.behaviour.places.at(village.movement.position("ana"))
    assert location is not None and location.id.startswith("terminal")


def test_reading_at_a_terminal_meets_curiosity_as_well_as_the_news() -> None:
    readers: list[str] = []
    village = Village([ANA], config=keen(A.NEWS))
    village.behaviour.hooks.set(
        read_news=lambda npc: readers.append(npc.id), news_interest=lambda npc: 1.0
    )
    village.run_until(lambda: bool(readers))
    needs = village.behaviour.minds["ana"].needs
    needs[Need.CURIOSITY] = needs[Need.NEWS] = 0.8

    village.run(minutes=4)

    assert village.behaviour.goal("ana").activity is A.NEWS
    assert village.behaviour.needs("ana")[Need.CURIOSITY] < 0.65
    assert village.behaviour.needs("ana")[Need.NEWS] < 0.6


def test_nobody_goes_to_a_terminal_with_nothing_worth_reading() -> None:
    village = Village([ANA], config=keen(A.NEWS))
    asked: list[str] = []

    def nothing(npc: Npc) -> float:
        asked.append(npc.id)
        return 0.0

    village.behaviour.hooks.set(news_interest=nothing)
    village.run(hours=2)

    assert asked and set(asked) == {"ana"}
    assert "news" not in {e.activity for _, e in village.goals}


def test_those_who_care_little_for_knowledge_rarely_read() -> None:
    readers = [
        make_npc(f"reader{n}", f"house_{n}", knowledge=0.9, open_mindedness=0.85) for n in (1, 2, 3)
    ]
    others = [
        make_npc(f"other{n}", f"house_{n}", knowledge=0.1, open_mindedness=0.2) for n in (4, 5, 6)
    ]
    village = Village([*readers, *others], start=at(9))
    village.behaviour.hooks.set(news_interest=lambda npc: 0.8)

    village.run(hours=8)

    visits = Counter(e.npc for _, e in village.goals if e.activity == "news")
    assert all(visits[npc.id] >= 3 for npc in readers)
    assert sum(visits[npc.id] for npc in others) <= 1


def test_a_failing_hook_is_logged_and_the_loop_carries_on(
    caplog: pytest.LogCaptureFixture,
) -> None:
    village = Village([ANA], config=keen(A.NEWS))

    def broken(npc: Npc) -> None:
        raise RuntimeError("no paper today")

    village.behaviour.hooks.set(read_news=broken, news_interest=lambda npc: 1.0)
    with caplog.at_level(logging.ERROR):
        village.run(hours=1)

    assert "no paper today" in caplog.text
    assert len(village.chosen("ana")) > 2


def test_hooks_put_back_only_what_they_replaced() -> None:
    village = Village([ANA])
    hooks = village.behaviour.hooks
    stubs = (hooks.request_conversation, hooks.read_news, hooks.conversations)

    restore_talk = hooks.set(request_conversation=lambda a, b: True, conversations=list)
    restore_news = hooks.set(read_news=lambda npc: None)
    restore_talk()

    assert (hooks.request_conversation, hooks.conversations) == (stubs[0], stubs[2])
    assert hooks.read_news is not stubs[1]
    restore_news()
    assert (hooks.request_conversation, hooks.read_news, hooks.conversations) == stubs


def test_the_stubs_decline_and_have_no_conversations() -> None:
    hooks = Village([ANA]).behaviour.hooks

    assert hooks.request_conversation("ana", "ben") is False
    assert hooks.read_news(ANA) is None
    assert hooks.conversations() == []


def test_the_same_seed_gives_the_same_day() -> None:
    npcs = [ANA, BEN, CAL]

    def day(seed: int) -> list[str]:
        village = Village(npcs, seed=seed)
        village.run(hours=2)
        return [f"{when:%H:%M:%S} {e}" for when, e in village.goals]

    assert day(7) == day(7)
    assert day(7) != day(8)


def test_state_is_json_for_the_debug_overlay() -> None:
    village = Village([ANA, crafter("wren", "house_2", Medium.WRITING)])
    village.run(hours=1)

    state = village.behaviour.state("ana")

    assert json.loads(json.dumps(state)) == state
    needs = state["needs"]
    assert isinstance(needs, dict) and set(needs) == {need.value for need in Need} - {
        "inspiration",
        "finances",
    }
    assert state["goal"] == str(village.behaviour.goal("ana"))
    assert "inspiration" in village.behaviour.state("wren")["needs"]


def test_npcs_already_on_the_map_stay_where_they_are() -> None:
    village = Village([ANA], placed={"ana": "square"}, config=keen(A.IDLE))

    location = village.behaviour.places.at(village.movement.position("ana"))
    assert location is not None and location.id == "square"
    assert village.behaviour.goal("ana").activity is A.IDLE


def test_places_others_are_heading_for_count_as_where_they_are() -> None:
    village = Village([ANA, BEN], config=keen(A.COFFEE_SHOP))
    village.run_until(lambda: village.behaviour.goal("ben").activity is A.COFFEE_SHOP)

    situation = village.behaviour._situation(village.behaviour.minds["ana"])

    assert [(o.id, o.place) for o in situation.others] == [("ben", "coffee_shop")]


def door_into(map_id: str) -> tuple[Point, Point]:
    door = next(d for d in MAPS[VILLAGE_MAP].doors if d.inside.map == map_id)
    outside, inside = door.outside, door.inside
    return Point(outside.x, outside.y, outside.map), Point(inside.x, inside.y, inside.map)


@pytest.mark.parametrize("activity", [A.COFFEE_SHOP, A.NOODLE_BAR, A.MAKER_SPACE, A.GALLERY])
def test_trips_inside_go_through_the_door_and_take_as_long_as_the_walk(activity: Activity) -> None:
    village = Village([ANA], config=keen(activity))
    spots: list[Point] = []
    village.world.bus.subscribe(EntityMoved, lambda e: spots.append(Point(e.x, e.y, e.map)))
    village.run_until(lambda: village.behaviour.minds["ana"].walk is not None)
    walk, left = village.behaviour.minds["ana"].walk, village.clock.now
    assert walk is not None
    village.run_until(lambda: walk.done)

    place = MAPS[activity.value].location(activity.value)
    here = village.movement.position("ana")
    assert walk.outcome is Outcome.ARRIVED
    assert here.map == place.map and inside(place, here)
    assert door_into(place.map) in zip(spots, spots[1:], strict=False)
    elapsed = (village.clock.now - left).total_seconds()
    assert elapsed == pytest.approx(walk.distance / WALKING_SPEED, abs=2 * STEP)


def test_residents_who_choose_the_coffee_shop_end_up_at_the_counter_inside() -> None:
    village = Village([ANA, BEN, CAL], config=keen(A.COFFEE_SHOP))
    minds = village.behaviour.minds.values()
    village.run_until(lambda: all(m.goal.activity is A.COFFEE_SHOP and not m.walk for m in minds))

    cafe = MAPS["coffee_shop"]
    [stand] = next(i for i in cafe.interactables if i.id == "coffee_shop_counter").stand
    spots = [village.movement.position(npc.id) for npc in (ANA, BEN, CAL)]
    assert Point(stand.x, stand.y, cafe.id) in spots
    assert all(inside(cafe.location("coffee_shop"), spot) for spot in spots)


def test_a_wander_from_inside_goes_out_near_the_door() -> None:
    village = Village([ANA], config=keen(A.WANDER), placed={"ana": "coffee_shop"})

    walk = village.behaviour.minds["ana"].walk
    outside, _ = door_into("coffee_shop")
    assert walk is not None and walk.destination is not None
    assert walk.destination.map == VILLAGE_MAP
    reach = DEFAULT_CONFIG.wander_radius
    assert abs(walk.destination.x - outside.x) <= reach
    assert abs(walk.destination.y - outside.y) <= reach


def test_only_someone_on_the_same_map_is_company() -> None:
    def social(ben: MapTile | None) -> float:
        placed: dict[str, str | MapTile] = {"ana": MapTile(map="coffee_shop", x=13, y=4)}
        if ben is not None:
            placed["ben"] = ben
        village = Village([ANA, BEN][: len(placed)], config=keen(A.IDLE), placed=placed)
        village.run(minutes=30)
        return village.behaviour.needs("ana")[Need.SOCIAL]

    alone = social(None)
    assert social(MapTile(map=VILLAGE_MAP, x=13, y=4)) == pytest.approx(alone)
    assert social(MapTile(map="coffee_shop", x=14, y=4)) < alone - 0.01


@pytest.mark.parametrize("chases", [0, 3])
def test_a_seeker_asks_to_talk_only_on_the_same_map_following_through_a_door(chases: int) -> None:
    requests: list[tuple[str, str]] = []
    village = Village(
        [ANA, BEN],
        start=at(11),
        config=keen(A.IDLE, chases=chases),
        placed={"ana": "house_1", "ben": MapTile(map=VILLAGE_MAP, x=10, y=12)},
    )

    def decline(a: str, b: str) -> bool:
        requests.append((a, b))
        return False

    seek = Goal(A.SEEK, "ben")
    village.behaviour.hooks.set(request_conversation=decline)
    village.behaviour.nudge("ana", seek, 100)
    village.run_until(lambda: village.behaviour.goal("ana") == seek)
    village.movement.place("ben", MapTile(map="coffee_shop", x=10, y=12))
    village.run_until(lambda: village.behaviour.goal("ana") != seek or bool(requests), minutes=5)

    ana, ben = (village.movement.position(npc) for npc in ("ana", "ben"))
    if chases:
        assert requests == [("ana", "ben")]
        assert (ana.map, ben.map) == ("coffee_shop", "coffee_shop")
    else:
        assert requests == []
        assert (ana.map, ben.map) == (VILLAGE_MAP, "coffee_shop")
        assert math.dist(ana, ben) <= DEFAULT_CONFIG.talk_range


def crafter(id: str, home: str, medium: Medium, **values: float) -> Npc:
    return make_npc(id, home, **values).model_copy(
        update={"craft": Craft(medium=medium, form="something")}
    )


WRITER = crafter("wren", "house_1", Medium.WRITING)
PAINTER = crafter("pia", "house_2", Medium.MURAL)
WALL = MuralSpot("wall_a", Tile(x=19, y=12))


class Made:
    def __init__(self, village: Village) -> None:
        self.village = village
        self.works: list[tuple[datetime, str, str | None]] = []

    def __call__(self, npc: Npc, wall: str | None, intention: Intention | None = None) -> None:
        self.works.append((self.village.clock.now, npc.id, wall))


def arrived(village: Village, npc: str) -> datetime:
    village.run_until(lambda: village.behaviour.goal(npc).activity is A.CREATE)
    village.run_until(lambda: village.behaviour.minds[npc].walk is None)
    return village.clock.now


def test_inspiration_rises_only_with_a_craft_and_faster_with_creativity() -> None:
    config = DEFAULT_CONFIG.model_copy(update={"start_dwell": (180, 180), "head_starts": 0})
    keen = crafter("keen", "house_1", Medium.WRITING, creativity=0.9)
    dull = crafter("dull", "house_2", Medium.WRITING, creativity=0.2)
    none = make_npc("none", "house_3", creativity=0.9)
    village = Village([keen, dull, none], config=config)
    assert village.behaviour.needs("none")[Need.INSPIRATION] == 0
    for mind in village.behaviour.minds.values():
        mind.needs[Need.INSPIRATION] = 0.1

    village.run(hours=2)

    rise = {npc: village.behaviour.needs(npc)[Need.INSPIRATION] - 0.1 for npc in ("keen", "dull")}
    assert rise["keen"] > 1.5 * rise["dull"] > 0
    assert village.behaviour.needs("none")[Need.INSPIRATION] == 0.1


def test_writers_hand_over_their_work_at_the_end_of_their_stay() -> None:
    village = Village([WRITER], config=keen(A.CREATE, head_starts=0))
    made = Made(village)
    village.behaviour.hooks.set(create=made)
    village.behaviour.minds["wren"].needs[Need.INSPIRATION] = 0.9

    there = arrived(village, "wren")
    assert made.works == []
    village.run_until(lambda: bool(made.works), minutes=90)

    when, npc, wall = made.works[0]
    low, high = DEFAULT_CONFIG.dwell[A.CREATE]
    assert (npc, wall) == ("wren", None)
    assert timedelta(minutes=low) <= when - there <= timedelta(minutes=high)
    assert village.behaviour.needs("wren")[Need.INSPIRATION] < 0.01


def test_muralists_paint_the_wall_the_hook_names_from_its_tile() -> None:
    village = Village([PAINTER], config=keen(A.CREATE))
    made = Made(village)
    village.behaviour.hooks.set(create=made, mural_wall=lambda npc: WALL)

    arrived(village, "pia")
    assert village.behaviour.goal("pia") == Goal(A.CREATE, "wall_a")
    assert village.movement.position("pia") == (WALL.tile.x, WALL.tile.y)
    village.run_until(lambda: bool(made.works), minutes=90)

    assert [(npc, wall) for _, npc, wall in made.works] == [("pia", "wall_a")]


def test_a_muralist_with_no_wall_never_creates() -> None:
    village = Village([PAINTER], config=keen(A.CREATE))
    asked: list[str] = []

    def nowhere(npc: Npc) -> None:
        asked.append(npc.id)

    village.behaviour.hooks.set(mural_wall=nowhere)
    village.behaviour.minds["pia"].needs[Need.INSPIRATION] = 1.0

    village.run(hours=3)

    assert asked and set(asked) == {"pia"}
    assert len(village.chosen("pia")) > 3
    assert "create" not in {e.activity for _, e in village.goals}


def test_a_stay_cut_short_makes_nothing() -> None:
    village = Village([WRITER], config=keen(A.CREATE, head_starts=0))
    made = Made(village)
    village.behaviour.hooks.set(create=made)
    village.behaviour.minds["wren"].needs[Need.INSPIRATION] = 0.9
    arrived(village, "wren")
    village.run(minutes=20)

    village.behaviour.nudge("wren", Goal(A.PARK, "park"), 50.0)
    village.run(minutes=0.1)

    assert village.behaviour.goal("wren") == Goal(A.PARK, "park")
    assert made.works == []
    assert village.behaviour.needs("wren")[Need.INSPIRATION] > 0.9


def test_a_talk_pauses_making_something_and_they_go_back_to_it() -> None:
    village = Village([WRITER, BEN], config=keen(A.CREATE, head_starts=0))
    made = Made(village)
    village.behaviour.hooks.set(create=made)
    there = arrived(village, "wren")
    writing = village.behaviour.goal("wren")
    planned = village.behaviour.minds["wren"].until
    assert planned is not None

    village.run(minutes=10)
    village.behaviour.pause("wren", "ben")
    village.run(minutes=15)
    village.behaviour.resume("wren")

    assert village.behaviour.goal("wren") == writing
    assert village.behaviour.minds["wren"].until == planned + timedelta(minutes=15)
    village.run_until(lambda: bool(made.works), minutes=90)
    assert made.works[0][0] - there >= timedelta(minutes=DEFAULT_CONFIG.dwell[A.CREATE][0] + 15)


def test_writing_at_home_keeps_seekers_away_and_writing_out_does_not() -> None:
    village = Village([WRITER, BEN], start=at(11), config=keen(A.IDLE))
    now = village.clock.now
    needs = village.behaviour.needs("wren")

    village.behaviour.restore("wren", Goal(A.CREATE, "house_1"), needs, now, now, {})
    assert village.behaviour.at_home("wren")
    assert not village.behaviour.available("ben", "wren")

    village.behaviour.restore("wren", Goal(A.CREATE, "coffee_shop"), needs, now, now, {})
    assert not village.behaviour.at_home("wren")
    assert village.behaviour.available("ben", "wren")


def test_a_restored_stay_making_something_still_finishes() -> None:
    village = Village([WRITER], config=keen(A.IDLE))
    made = Made(village)
    village.behaviour.hooks.set(create=made)
    now = village.clock.now
    needs = village.behaviour.needs("wren")

    village.behaviour.restore(
        "wren", Goal(A.CREATE, "house_1"), needs, now, now + timedelta(minutes=10), {}
    )
    village.run(minutes=11)

    assert [(npc, wall) for _, npc, wall in made.works] == [("wren", None)]


def test_the_new_stubs_make_nothing_and_pick_no_wall() -> None:
    hooks = Village([ANA]).behaviour.hooks

    assert hooks.create(WRITER, None, None) is None
    assert hooks.mural_wall(PAINTER) is None
