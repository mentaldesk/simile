import json
import logging
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from simile.behaviour import (
    DEFAULT_CONFIG,
    Activity,
    Behaviour,
    BehaviourConfig,
    Goal,
    GoalChosen,
    Need,
)
from simile.npc import load_npcs
from simile.schema import PLAYER_ID, Baseline, CoreValue, Npc, Relationship
from simile.sim import STEP, Clock, FakeWallClock, World
from simile.world import Movement
from simile.world.map import load_map
from simile.world.movement import inside

TOWN = load_map()
MORNING = datetime(2026, 1, 1, 8, tzinfo=UTC)
TEMPLATE = load_npcs()[0]
A = Activity


def make_npc(id: str, home: str, **values: float) -> Npc:
    """An NPC who cares about everything at 0.5, except the values given."""
    scores = {value: values.get(value.value, 0.5) for value in CoreValue}
    return TEMPLATE.model_copy(
        update={"id": id, "name": id.title(), "home": home, "values": scores}
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
        placed: dict[str, str] | None = None,
    ) -> None:
        self.world = World(Clock(start), FakeWallClock())
        self.movement = Movement(TOWN, self.world.bus)
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
    village = Village([ANA])
    village.run(hours=1)

    state = village.behaviour.state("ana")

    assert json.loads(json.dumps(state)) == state
    needs = state["needs"]
    assert isinstance(needs, dict) and set(needs) == {"social", "curiosity", "rest", "news"}
    assert state["goal"] == str(village.behaviour.goal("ana"))


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
