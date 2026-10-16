import asyncio
import itertools
import sys
import types
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest

from simile.behaviour import Activity, Behaviour, Goal
from simile.conversation import (
    DEFAULT_CONFIG,
    ConversationConfig,
    ConversationEngine,
    Facing,
    LineDrafted,
)
from simile.llm import CallRecord, FakeProvider, LLMClient, LLMError, Request
from simile.memory import MemoryStore
from simile.npc import load_npcs
from simile.schema import (
    PLAYER_ID,
    Aspect,
    CoreValue,
    InteractionEvent,
    Line,
    Memory,
    MemoryKind,
    Npc,
    Relationship,
)
from simile.sim import (
    Clock,
    ConversationEnded,
    ConversationStarted,
    Event,
    FakeWallClock,
    LineSpoken,
    World,
)
from simile.social import meet
from simile.world import Movement
from simile.world.map import load_map

pytestmark = pytest.mark.anyio

TOWN = load_map()
START = datetime(2026, 1, 1, 10, tzinfo=UTC)
TEMPLATE = load_npcs()[0]


def make_npc(id: str, home: str, **values: float) -> Npc:
    """An NPC who cares about everything at 0.5, except the values given."""
    scores = {value: values.get(value.value, 0.5) for value in CoreValue}
    return TEMPLATE.model_copy(
        update={"id": id, "name": f"{id.title()} Test", "home": home, "values": scores}
    )


ANA = make_npc("ana", "house_1", tradition=0.0, justice=1.0)
BEN = make_npc("ben", "house_2", tradition=0.0, justice=1.0)
CAL = make_npc("cal", "house_3")
DOT = make_npc("dot", "house_4")


def feeling(owner: Npc, about: str, **scores: float) -> Relationship:
    return meet(owner, about).model_copy(update=scores)


def friends(a: Npc, b: Npc) -> list[Relationship]:
    return [feeling(a, b.id, like=0.9, trust=0.8), feeling(b, a.id, like=0.9, trust=0.8)]


class Script:
    """Replies in turn, recording when each was asked for."""

    def __init__(self, clock: Clock, replies: Sequence[str]) -> None:
        self.clock = clock
        self.replies = itertools.cycle(replies)
        self.calls: list[tuple[datetime, Request]] = []

    def __call__(self, request: Request) -> str:
        self.calls.append((self.clock.now, request))
        return next(self.replies)

    @property
    def prompts(self) -> list[str]:
        return [request.messages[-1].content for _, request in self.calls]


class Village:
    """NPCs at the coffee shop with movement and a conversation engine on a fake wall clock.
    Their behaviour doesn't tick, so they only talk when a test starts it."""

    def __init__(
        self,
        replies: Sequence[str] = ("Lovely morning for it. [values: connection]",),
        *,
        npcs: Sequence[Npc] = (ANA, BEN),
        relationships: Sequence[Relationship] = (),
        config: ConversationConfig = DEFAULT_CONFIG,
        provider: FakeProvider | None = None,
    ) -> None:
        self.world = World(Clock(START), FakeWallClock())
        self.store = MemoryStore(":memory:")
        self.store.add(*relationships)
        self.movement = Movement(TOWN, self.world.bus)
        for npc in npcs:
            self.movement.place(npc.id, "coffee_shop")
        self.behaviour = Behaviour(
            self.world.clock, self.world.bus, self.movement, npcs, self.store, seed=0
        )
        self.behaviour.start()
        self.script = Script(self.clock, replies)
        self.provider = provider or FakeProvider(itertools.repeat(self.script, 100))
        self.records: list[CallRecord] = []
        self.llm = LLMClient(self.provider, listeners=[self.records.append])
        self.engine = ConversationEngine(
            self.clock,
            self.world.bus,
            self.behaviour,
            self.store,
            lambda: self.llm,
            config=config,
            seed=0,
        )
        self.events: list[Event] = []
        self.world.bus.subscribe(Event, self.events.append)
        self.world.loop.register(self.movement)
        self.world.loop.register(self.engine)

    @property
    def clock(self) -> Clock:
        return self.world.clock

    async def run(self, minutes: float = 3) -> None:
        await self.world.loop.run(timedelta(minutes=minutes))

    def of[E: Event](self, kind: type[E]) -> list[E]:
        return [event for event in self.events if isinstance(event, kind)]

    @property
    def spoken(self) -> list[Line]:
        return [event.line for event in self.of(LineSpoken)]

    @property
    def ended(self) -> list[ConversationEnded]:
        return self.of(ConversationEnded)


async def test_a_friend_accepts_and_they_stop_and_face_each_other() -> None:
    village = Village(relationships=friends(ANA, BEN))

    assert village.engine.request("ana", "ben")

    started = village.of(ConversationStarted)
    assert [event.conversation.participants for event in started] == [["ana", "ben"]]
    assert started[0].conversation.started == START
    assert village.behaviour.goal("ana") == Goal(Activity.TALK, "ben")
    assert village.behaviour.goal("ben") == Goal(Activity.TALK, "ana")
    assert all(mind.paused and mind.walk is None for mind in village.behaviour.minds.values())
    facing = {event.entity: event for event in village.of(Facing)}
    assert facing["ana"].toward == "ben" and facing["ben"].toward == "ana"
    opposite = {"left": "right", "right": "left", "up": "down", "down": "up"}
    assert opposite[facing["ana"].direction] == facing["ben"].direction
    assert [c.id for c in village.engine.live()] == [started[0].conversation.id]
    assert village.engine.state("ben") == {
        "conversation": started[0].conversation.id,
        "talking_to": "ana",
        "engagement": 0.84,
        "facing": facing["ben"].direction,
        "leaving": False,
    }


async def test_someone_who_dislikes_them_declines() -> None:
    disliked = [feeling(BEN, "ana", like=0.05, trust=0.1)]
    village = Village(relationships=disliked)

    assert not village.engine.request("ana", "ben")

    assert village.events == []
    assert not village.engine.talking("ana")


async def test_the_player_is_left_to_player_conversations() -> None:
    village = Village()

    assert not village.engine.request("ana", PLAYER_ID)


async def test_concurrent_conversations_are_capped() -> None:
    village = Village(
        npcs=(ANA, BEN, CAL, DOT),
        relationships=[*friends(ANA, BEN), *friends(CAL, DOT)],
        config=ConversationConfig(max_conversations=1),
    )

    assert village.engine.request("ana", "ben")
    assert not village.engine.request("cal", "dot")
    assert not village.engine.request("dot", "ana")


async def test_lines_take_as_long_as_saying_them_and_are_written_one_ahead() -> None:
    replies = ["One two three four five. [values: connection]", "Six seven eight nine ten."]
    village = Village(replies, relationships=friends(ANA, BEN))
    village.engine.start("ana", "ben")

    await village.run(minutes=1)

    lines = village.spoken
    assert len(lines) > 4
    assert [line.speaker for line in lines[:4]] == ["ana", "ben", "ana", "ben"]
    assert [line.text for line in lines[:2]] == [
        "One two three four five.",
        "Six seven eight nine ten.",
    ]
    assert {line.duration for line in lines} == {1.5}
    for line, after in itertools.pairwise(lines):
        assert after.timestamp == line.timestamp + timedelta(seconds=1.5 + 0.5)
    asked = [when for when, _ in village.script.calls]
    for line, next_asked in zip(lines, asked[1:], strict=False):
        assert line.timestamp <= next_asked < line.timestamp + timedelta(seconds=line.duration)


async def test_each_line_is_announced_before_it_is_spoken() -> None:
    village = Village(relationships=friends(ANA, BEN))
    village.engine.start("ana", "ben")

    await village.run(minutes=1)

    order = [
        (type(event).__name__, event.line.id)
        for event in village.events
        if isinstance(event, LineDrafted | LineSpoken)
    ]
    spoken = [line.id for line in village.spoken]
    for line_id in spoken:
        assert order.index(("LineDrafted", line_id)) < order.index(("LineSpoken", line_id))
    drafted = [event.line for event in village.of(LineDrafted)]
    assert drafted[: len(spoken)] == village.spoken


async def test_a_slow_line_waits_and_the_conversation_carries_on() -> None:
    release = asyncio.Event()
    village = Village(relationships=friends(ANA, BEN))
    village.provider.replies.appendleft(["Sorry, ", "where was I? ", release])
    village.provider.replies.appendleft("Hello! [values: connection]")

    class Release:
        def tick(self, dt: float) -> None:
            if village.clock.now >= START + timedelta(seconds=30):
                release.set()

    village.world.loop.register(Release())
    village.engine.start("ana", "ben")
    await village.run(minutes=1)

    first, second = village.spoken[:2]
    assert first.text == "Hello!"
    assert second.text == "Sorry, where was I?"
    assert second.timestamp >= START + timedelta(seconds=30)
    assert len(village.spoken) > 2


async def test_a_conversation_on_topics_they_dislike_ends_with_a_goodbye() -> None:
    village = Village(["Tradition matters. [values: tradition]"])
    village.engine.start("ana", "ben")

    await village.run()

    [ended] = village.ended
    conversation = ended.conversation
    assert [line.speaker for line in conversation.lines] == ["ana", "ben", "ana", "ben"]
    assert conversation.lines == village.spoken
    last = village.spoken[-1]
    assert conversation.ended == last.timestamp + timedelta(seconds=last.duration)
    prompts = village.script.prompts
    assert "You've just walked up to Ben." in prompts[0]
    assert "Say your next line to Ana." in prompts[1]
    assert "goodbye to Ben." in prompts[2]
    assert "Ana is leaving. Say a brief goodbye back." in prompts[3]
    assert len(prompts) == 4
    assert village.engine.live() == []
    assert not any(mind.paused for mind in village.behaviour.minds.values())
    cooldown = conversation.ended + timedelta(minutes=DEFAULT_CONFIG.cooldown)
    assert village.behaviour.minds["ana"].cooldowns["ben"] == cooldown
    assert village.behaviour.minds["ben"].cooldowns["ana"] == cooldown


async def test_topics_they_care_about_keep_them_talking() -> None:
    village = Village(["That's not fair on them. [values: justice]"])
    village.engine.start("ana", "ben")

    await village.run(minutes=5)

    [ended] = village.ended
    assert len(ended.conversation.lines) == DEFAULT_CONFIG.max_lines
    assert "goodbye to" in village.script.prompts[-2]


async def test_a_pair_who_dislike_each_other_talk_less_than_friends() -> None:
    enemies = [feeling(ANA, "ben", like=0.15), feeling(BEN, "ana", like=0.15)]
    lengths = []
    for relationships in (enemies, friends(ANA, BEN)):
        village = Village(["Hm. Right."], relationships=relationships)
        village.engine.start("ana", "ben")
        await village.run(minutes=5)
        [ended] = village.ended
        lengths.append(len(ended.conversation.lines))

    assert lengths[0] == DEFAULT_CONFIG.min_lines + 2
    assert lengths[0] < lengths[1]


async def test_a_failed_line_ends_the_conversation() -> None:
    provider = FakeProvider(["Hello. [values: connection]", LLMError("usage limit reached")])
    village = Village(relationships=friends(ANA, BEN), provider=provider)
    village.engine.start("ana", "ben")

    await village.run()

    [ended] = village.ended
    assert [line.text for line in ended.conversation.lines] == ["Hello."]
    assert ended.conversation.ended == village.spoken[0].timestamp + timedelta(seconds=1.5)
    assert not any(mind.paused for mind in village.behaviour.minds.values())


async def test_the_prompt_brings_in_the_relationship_memories_history_and_news(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def topics_to_raise(memory: object, npc_id: str, now: datetime, k: int = 3) -> list[Memory]:
        return [
            Memory(
                owner=npc_id,
                kind=MemoryKind.NEWS,
                content=f"{npc_id} read that octopuses dream.",
                salience=0.9,
                valence=0.6,
                timestamp=now,
            )
        ]

    reactions = types.ModuleType("simile.news.reactions")
    reactions.topics_to_raise = topics_to_raise  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "simile.news.reactions", reactions)
    village = Village(relationships=[feeling(ANA, "ben", like=0.95, familiarity=0.8)])
    village.store.add(
        Memory(
            owner="ana",
            kind=MemoryKind.CONVERSATION,
            content="Ben lent me his ladder.",
            salience=0.7,
            valence=0.5,
            timestamp=START - timedelta(hours=1),
            about=["ben"],
        ),
        InteractionEvent(
            actor="ben",
            target="ana",
            action="fixed her bike",
            aspects=[Aspect.LIKE],
            valence=0.6,
            magnitude=0.5,
            timestamp=START - timedelta(days=2),
        ),
    )
    village.engine.start("ana", "ben")

    await village.run(minutes=0.1)

    _, request = village.script.calls[0]
    prompt = request.messages[-1].content
    assert ANA.persona in request.system
    assert "You like Ben a lot" in prompt
    assert "You know them well." in prompt
    assert "- 2 days ago, Ben: fixed her bike" in prompt
    assert "- Ben lent me his ladder." in prompt
    assert "- ana read that octopuses dream." in prompt
    assert "at The Daily Grind" in prompt
    assert request.model == "claude-haiku-5-5"


async def test_without_news_reactions_there_are_no_topics(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "simile.news.reactions", None)
    village = Village(relationships=friends(ANA, BEN))
    village.engine.start("ana", "ben")

    await village.run(minutes=0.1)

    assert "News you might bring up" not in village.script.prompts[0]


async def test_news_they_reacted_to_comes_up() -> None:
    village = Village(relationships=friends(ANA, BEN))
    village.store.add(
        Memory(
            owner="ana",
            kind=MemoryKind.NEWS,
            content="The river is getting a tidal barrier, and about time.",
            salience=0.9,
            valence=0.6,
            timestamp=START - timedelta(hours=1),
            news_id="barrier",
        )
    )
    village.engine.start("ana", "ben")

    await village.run(minutes=0.1)

    news = "News you might bring up:\n- The river is getting a tidal barrier, and about time."
    assert news in village.script.prompts[0]
    assert news not in village.script.prompts[1]


async def test_line_ids_are_unique_across_conversations() -> None:
    village = Village(
        npcs=(ANA, BEN, CAL, DOT), relationships=[*friends(ANA, BEN), *friends(CAL, DOT)]
    )
    village.engine.start("ana", "ben")
    village.engine.start("cal", "dot")

    await village.run(minutes=1)

    ids = [line.id for line in village.spoken]
    assert len({line.conversation_id for line in village.spoken}) == 2
    assert len(ids) == len(set(ids))


async def test_finished_conversations_stay_reachable() -> None:
    village = Village(["Tradition matters. [values: tradition]"])
    started = village.engine.start("ana", "ben")

    await village.run()

    finished = village.engine.conversation(started.id)
    assert finished is not None
    assert finished == village.ended[0].conversation
    assert len(finished.lines) == 4
    assert village.engine.state("ana") == {"conversation": None}
    assert village.engine.conversation("nope") is None


async def test_closing_stops_writing() -> None:
    hang = asyncio.Event()
    provider = FakeProvider([["Well", hang]])
    village = Village(provider=provider)
    village.engine.start("ana", "ben")
    await village.run(minutes=0.1)

    assert provider.requests
    assert village.records == []

    await asyncio.wait_for(village.engine.close(), 1)

    assert village.spoken == []
    assert [record.error for record in village.records] == ["cancelled"]


async def test_a_line_that_never_comes_back_times_out_and_frees_its_slots() -> None:
    never = asyncio.Event()
    provider = FakeProvider(["Hello. [values: connection]", ["Well, ", never], "Free again."])
    village = Village(
        relationships=friends(ANA, BEN),
        config=ConversationConfig(line_timeout=0.05),
        provider=provider,
    )
    village.llm = LLMClient(provider, max_concurrency=1, listeners=[village.records.append])
    village.engine.start("ana", "ben")

    await village.run(minutes=0.1)
    await asyncio.sleep(0.1)
    await village.run(minutes=0.1)

    [ended] = village.ended
    assert [line.text for line in ended.conversation.lines] == ["Hello."]
    assert [record.error for record in village.records] == [None, "cancelled"]
    assert village.engine.live() == []
    assert not any(mind.paused for mind in village.behaviour.minds.values())
    assert await asyncio.wait_for(village.llm.complete("Still there?"), 1) == "Free again."
