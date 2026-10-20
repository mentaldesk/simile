from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest

from simile.ambient import AmbientConfig, Director, Earshot, Nudged
from simile.behaviour import Activity, Behaviour, Goal
from simile.conversation import DEFAULT_CONFIG, ConversationConfig, ConversationEngine
from simile.conversation.player import PlayerConversations
from simile.llm import FakeProvider, LLMClient
from simile.llm.fake import scene
from simile.memory import MemoryStore
from simile.npc import load_npcs
from simile.schema import PLAYER_ID, Conversation, CoreValue, MapTile, Npc, Relationship
from simile.sim import (
    Clock,
    ConversationEnded,
    ConversationStarted,
    Event,
    FakeWallClock,
    World,
)
from simile.social import meet
from simile.voicing import VoicingConfig
from simile.world import Movement, Point
from simile.world.map import load_maps

MAPS = load_maps()
START = datetime(2026, 1, 1, 11, tzinfo=UTC)
TEMPLATE = load_npcs()[0]
STREET, ROW = "high_street", 15
"""The High Street's row, through the square."""
PLAYER_AT = 55
INSIDE = "coffee_shop_floor_0"


def make_npc(id: str, home: str) -> Npc:
    scores = {value: 0.5 for value in CoreValue}
    return TEMPLATE.model_copy(
        update={
            "id": id,
            "name": f"{id.title()} Test",
            "home": home,
            "values": scores,
            "workplace": None,
            "shifts": [],
            "pay": None,
        }
    )


ANA, BEN, CAL, DOT = (
    make_npc(id, f"house_{n}") for n, id in enumerate(["ana", "ben", "cal", "dot"], 1)
)
QUICK = AmbientConfig(quiet=60, retry=30)
ALWAYS = DEFAULT_CONFIG.model_copy(update={"accept_temperature": 0})
"""Accepts whenever they're more for it than against."""


def feeling(owner: Npc, about: Npc, like: float) -> Relationship:
    return meet(owner, about.id).model_copy(update={"like": like, "trust": like})


def friends(a: Npc, b: Npc) -> list[Relationship]:
    return [feeling(a, b, 0.9), feeling(b, a, 0.9)]


class Village:
    """NPCs out in the square with the player, a conversation engine and the director, on a
    fake wall clock. Everyone's needs are middling and nobody decides until a test says so."""

    def __init__(
        self,
        columns: dict[str, int],
        *,
        relationships: Sequence[Relationship] = (),
        config: AmbientConfig = QUICK,
        engine: ConversationConfig = ALWAYS,
    ) -> None:
        npcs = [npc for npc in (ANA, BEN, CAL, DOT) if npc.id in columns]
        self.world = World(Clock(START), FakeWallClock())
        self.store = MemoryStore(":memory:")
        self.store.add(*relationships)
        self.movement = Movement(MAPS, self.world.bus)
        for npc, column in columns.items():
            self.movement.place(npc, MapTile(map=STREET, x=column, y=ROW))
        self.movement.place(PLAYER_ID, MapTile(map=STREET, x=PLAYER_AT, y=ROW))
        self.behaviour = Behaviour(
            self.world.clock, self.world.bus, self.movement, npcs, self.store, seed=0
        )
        self.behaviour.start()
        for npc, mind in self.behaviour.minds.items():
            needs = {need: 0.5 for need in mind.needs}
            later = START + timedelta(hours=1)
            self.behaviour.restore(npc, Goal(Activity.SQUARE, "square"), needs, START, later, {})
        llm = LLMClient(
            FakeProvider(default=lambda request: scene(request, ["Lovely morning."]) or "Morning.")
        )
        self.engine = ConversationEngine(
            self.clock, self.world.bus, self.behaviour, self.store, lambda: llm, config=engine
        )
        self.behaviour.hooks.set(request_conversation=self.engine.request)
        self.connected = True
        self.director = Director(
            self.behaviour, self.engine, connected=lambda: self.connected, config=config
        )
        self.world.bus.subscribe(ConversationStarted, self.director.earshot.on_started)
        self.world.bus.subscribe(ConversationEnded, self.director.earshot.on_ended)
        self.events: list[Event] = []
        self.world.bus.subscribe(Event, self.events.append)

    @property
    def clock(self) -> Clock:
        return self.world.clock

    def wait(self, seconds: float) -> None:
        self.clock.advance(seconds)

    def at_home(self, npc: str, activity: Activity = Activity.HOME) -> None:
        self.behaviour.minds[npc].goal = Goal(activity, self.behaviour.npcs[npc].home)

    async def run(self, minutes: float) -> None:
        for system in (self.behaviour, self.movement, self.engine, self.director):
            self.world.loop.register(system)
        await self.world.loop.run(timedelta(minutes=minutes))

    def of[E: Event](self, kind: type[E]) -> list[E]:
        return [event for event in self.events if isinstance(event, kind)]


def test_chooses_friends_over_strangers() -> None:
    village = Village({"ana": 51, "ben": 59, "cal": 53, "dot": 57}, relationships=friends(ANA, BEN))

    assert set(village.director.choose() or ()) == {"ana", "ben"}


def test_the_keenest_pair_wins_and_the_target_is_the_one_nearer_the_player() -> None:
    village = Village(
        {"ana": 49, "ben": 57, "cal": 53, "dot": 61},
        relationships=[
            *friends(ANA, BEN),
            feeling(CAL, DOT, 0.7),
            feeling(DOT, CAL, 0.7),
        ],
    )

    assert village.director.choose() == ("ana", "ben")


def test_a_pair_where_one_dislikes_the_other_is_left_alone() -> None:
    village = Village(
        {"ana": 51, "ben": 59}, relationships=[feeling(ANA, BEN, 0.9), feeling(BEN, ANA, 0.0)]
    )

    assert village.engine.accept_score("ben", "ana") > 0
    assert village.engine.accept_score("ana", "ben") <= 0
    assert village.director.choose() is None


def test_the_target_is_in_earshot_and_the_seeker_within_reach() -> None:
    far = Village({"ana": 44, "ben": 66}, relationships=friends(ANA, BEN))
    assert far.director.choose() is None

    out_of_reach = Village(
        {"ana": 51, "ben": 59},
        relationships=friends(ANA, BEN),
        config=AmbientConfig(reach=6),
    )
    assert out_of_reach.director.choose() is None


def test_nobody_talking_or_walking_off_is_the_target() -> None:
    village = Village({"ana": 51, "ben": 59}, relationships=friends(ANA, BEN))
    village.behaviour.minds["ben"].walk = village.movement.walk_to("ben", "park")

    assert village.director.choose() == ("ben", "ana")

    village.behaviour.pause("ana")
    assert village.director.choose() is None


@pytest.mark.parametrize("activity", [Activity.HOME, Activity.SLEEP])
def test_nobody_at_home_or_asleep_is_nudged_or_sought_out(activity: Activity) -> None:
    village = Village({"ana": 51, "ben": 59}, relationships=friends(ANA, BEN))
    village.at_home("ana", activity)

    assert village.director.choose() is None


def test_nobody_in_a_house_is_nudged_or_sought_out() -> None:
    village = Village({"ana": 51, "ben": 48}, relationships=friends(ANA, BEN))
    village.movement.place(PLAYER_ID, MapTile(map="lychee_lane", x=22, y=15))
    village.movement.place("ben", MapTile(map="lychee_lane", x=26, y=15))
    village.movement.place("ana", MapTile(map="house_3_floor_0", x=3, y=2))

    assert village.director.choose() is None

    village.movement.place("ana", MapTile(map="lychee_lane", x=20, y=15))
    assert set(village.director.choose() or ()) == {"ana", "ben"}


def test_only_residents_on_the_players_map_are_nudged() -> None:
    village = Village({"ana": 51, "ben": 59}, relationships=friends(ANA, BEN))
    village.movement.track(PLAYER_ID, Point(11, 2, INSIDE))

    assert village.director.choose() is None

    for npc, x in (("ana", 8), ("ben", 14)):
        village.movement.place(npc, MapTile(map=INSIDE, x=x, y=2))
    assert set(village.director.choose() or ()) == {"ana", "ben"}


def test_a_seeker_outside_is_within_reach_of_a_target_inside_through_the_door() -> None:
    def choose(reach: float) -> tuple[str, str] | None:
        village = Village(
            {"ana": 51, "ben": 59},
            relationships=friends(ANA, BEN),
            config=AmbientConfig(reach=reach),
        )
        village.movement.track(PLAYER_ID, Point(11, 2, INSIDE))
        village.movement.place("ben", MapTile(map=INSIDE, x=8, y=2))
        village.movement.place("ana", MapTile(map=STREET, x=40, y=ROW))
        return village.director.choose()

    assert choose(24) == ("ana", "ben")
    assert choose(5) is None


def test_the_player_inside_the_coffee_shop_doesnt_hear_a_conversation_outside() -> None:
    village = Village({"ana": 40, "ben": 41}, relationships=friends(ANA, BEN))
    village.engine.start("ana", "ben")
    village.movement.track(PLAYER_ID, Point(15, 2, INSIDE))

    assert village.director.earshot.update() == set()

    village.movement.track(PLAYER_ID, Point(38, ROW, STREET))
    assert len(village.director.earshot.update()) == 1


def test_a_pair_cooling_off_from_each_other_is_left_alone() -> None:
    village = Village({"ana": 51, "ben": 59}, relationships=friends(ANA, BEN))
    village.behaviour.minds["ben"].cooldowns["ana"] = START + timedelta(minutes=30)

    assert village.director.choose() is None


def test_nudges_once_it_has_been_quiet_and_waits_before_the_next() -> None:
    village = Village({"ana": 51, "ben": 59}, relationships=friends(ANA, BEN))

    village.wait(59)
    assert village.director.look() is None

    village.wait(1)
    pair = village.director.look()
    assert pair is not None and set(pair) == {"ana", "ben"}
    assert [(e.seeker, e.target) for e in village.of(Nudged)] == [pair]

    village.wait(29)
    assert village.director.look() is None
    village.wait(1)
    assert village.director.look() is not None


def test_it_never_nudges_while_the_player_talks_and_the_quiet_starts_again_after() -> None:
    village = Village({"ana": 51, "ben": 59, "cal": 54}, relationships=friends(ANA, BEN))
    chat = PlayerConversations(village.engine).start("cal", opener=PLAYER_ID)

    village.wait(120)
    assert village.director.look() is None
    village.engine.end(chat.id)

    village.wait(59)
    assert village.director.look() is None
    village.wait(1)
    assert village.director.look() is not None


def test_by_default_it_nudges_after_a_minute_of_quiet_and_a_minute_apart() -> None:
    village = Village(
        {"ana": 51, "ben": 59}, relationships=friends(ANA, BEN), config=AmbientConfig()
    )

    village.wait(59)
    assert village.director.look() is None
    village.wait(1)
    assert village.director.look() is not None

    village.wait(59)
    assert village.director.look() is None
    village.wait(1)
    assert village.director.look() is not None


def test_a_conversation_in_earshot_keeps_it_from_nudging() -> None:
    village = Village({"ana": 51, "ben": 59, "cal": 53, "dot": 57}, relationships=friends(ANA, BEN))
    village.engine.start("cal", "dot")

    village.wait(120)
    assert village.director.look() is None
    village.engine.end(next(iter(village.director.earshot.live)))

    village.wait(59)
    assert village.director.look() is None
    village.wait(1)
    assert village.director.look() is not None


def test_nothing_happens_without_a_player_listening_or_when_turned_off() -> None:
    village = Village({"ana": 51, "ben": 59}, relationships=friends(ANA, BEN))
    village.connected = False
    village.wait(120)
    assert village.director.look() is None

    village.connected = True
    village.wait(59)
    assert village.director.look() is None

    village.director.config = AmbientConfig(enabled=False, quiet=60)
    village.wait(60)
    assert village.director.look() is None


def test_conversations_beyond_the_cap_are_not_nudged_for() -> None:
    village = Village(
        {"ana": 51, "ben": 59, "cal": 41, "dot": 42},
        relationships=friends(ANA, BEN),
        engine=ALWAYS.model_copy(update={"max_conversations": 1}),
    )
    village.engine.start("cal", "dot")

    village.wait(120)
    assert village.director.look() is None


@pytest.mark.anyio
async def test_a_nudged_resident_walks_over_and_asks_through_b2() -> None:
    village = Village({"ana": 49, "ben": 59}, relationships=friends(ANA, BEN))

    await village.run(minutes=1.5)

    nudged = village.of(Nudged)
    assert [(e.seeker, e.target) for e in nudged] == [("ana", "ben")]
    started = village.of(ConversationStarted)
    assert [e.conversation.participants for e in started] == [["ana", "ben"]]
    assert village.movement.distance("ana", "ben") <= village.behaviour.config.talk_range


def test_earshot_comes_in_at_earshot_and_goes_beyond_out_of_earshot() -> None:
    distances = {"ana": 9.0, "ben": 12.0}
    earshot = Earshot(distances.get, AmbientConfig(earshot=8, out_of_earshot=11))
    conversation = Conversation(id="c", participants=["ana", "ben"], started=START)
    earshot.on_started(ConversationStarted(conversation))
    mine = Conversation(id="p", participants=[PLAYER_ID, "cal"], started=START)
    earshot.on_started(ConversationStarted(mine))

    heard = []
    for ana in (9.0, 8.0, 10.5, 11.5, 10.5):
        distances["ana"] = ana
        heard.append(bool(earshot.update()))

    assert heard == [False, True, True, False, False]
    assert list(earshot.live) == ["c"]
    earshot.on_ended(ConversationEnded(conversation))
    assert earshot.update() == set()


def test_earshot_is_i1s_by_default() -> None:
    ambient, voicing = AmbientConfig(), VoicingConfig()

    assert (ambient.earshot, ambient.out_of_earshot) == (voicing.earshot, voicing.out_of_earshot)


def test_unknown_positions_are_out_of_earshot() -> None:
    earshot = Earshot(lambda npc: None)
    conversation = Conversation(id="c", participants=["ana", "ben"], started=START)
    earshot.on_started(ConversationStarted(conversation))

    assert earshot.update() == set()
