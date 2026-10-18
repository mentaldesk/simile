import asyncio
import itertools
import sys
import types
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta

import pytest

from simile.behaviour import Activity, Behaviour, Goal, Need
from simile.conversation import (
    DEFAULT_CONFIG,
    ConversationConfig,
    ConversationEngine,
    Facing,
    LineDrafted,
    engine,
)
from simile.conversation.engine import GOODBYES, Scene
from simile.conversation.player import PlayerConversations
from simile.llm import CallRecord, FakeProvider, LLMClient, LLMError, Request
from simile.memory import MemoryStore
from simile.npc import load_npcs
from simile.reflection import Extraction, Reflector
from simile.schema import (
    PLAYER_ID,
    Aspect,
    CoreValue,
    Flag,
    FlagKind,
    InteractionEvent,
    Line,
    MapTile,
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
from simile.voice import SpeakingRate
from simile.world import Movement
from simile.world.map import load_maps

from .conftest import remembers, work

pytestmark = pytest.mark.anyio

MAPS = load_maps()
CAFE = MapTile(map="coffee_shop", x=13, y=8)
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


def script(*lines: str, values: str = "connection") -> str:
    """Lines that take turns from Ana, each with a values tag."""
    speakers = itertools.cycle(["Ana", "Ben"])
    return "".join(f"{next(speakers)}: {line} [values: {values}]\n" for line in lines)


CHAT = script(
    "Morning, Ben!",
    "Morning. Lovely day.",
    "It is. Right, I'll let you get on.",
    "Bye then.",
)


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
        replies: Sequence[str] = (CHAT,),
        *,
        npcs: Sequence[Npc] = (ANA, BEN),
        relationships: Sequence[Relationship] = (),
        config: ConversationConfig = DEFAULT_CONFIG,
        provider: FakeProvider | None = None,
    ) -> None:
        self.world = World(Clock(START), FakeWallClock())
        self.store = MemoryStore(":memory:")
        self.store.add(*relationships)
        self.movement = Movement(MAPS, self.world.bus)
        for npc in npcs:
            self.movement.place(npc.id, CAFE)
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

    async def run_until(self, done: Callable[[], bool], minutes: float = 3) -> None:
        stop = self.clock.now + timedelta(minutes=minutes)
        while not done():
            assert self.clock.now < stop, "timed out"
            await self.world.loop.run(timedelta(seconds=0.1))

    def of[E: Event](self, kind: type[E]) -> list[E]:
        return [event for event in self.events if isinstance(event, kind)]

    @property
    def spoken(self) -> list[Line]:
        return [event.line for event in self.of(LineSpoken)]

    @property
    def drafted(self) -> list[Line]:
        return [event.line for event in self.of(LineDrafted)]

    @property
    def ended(self) -> list[ConversationEnded]:
        return self.of(ConversationEnded)

    def scene(self) -> Scene:
        [scene] = [talk for talk in self.engine._talks.values() if isinstance(talk, Scene)]
        return scene


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
        "engagement": village.scene().plan.stances["ben"].keen,
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


async def test_the_players_conversation_does_not_count_against_the_cap() -> None:
    village = Village(
        npcs=(ANA, BEN, CAL),
        relationships=friends(ANA, BEN),
        config=ConversationConfig(max_conversations=1),
    )
    PlayerConversations(village.engine).start("cal", opener=PLAYER_ID)

    assert village.engine.talking(PLAYER_ID)
    assert village.engine.request("ana", "ben")


async def test_a_request_is_decided_on_the_accept_score() -> None:
    disliked = [feeling(BEN, "ana", like=0.05, trust=0.1), *friends(CAL, DOT)]
    village = Village(
        npcs=(ANA, BEN, CAL, DOT),
        relationships=disliked,
        config=ConversationConfig(accept_temperature=0),
    )

    assert village.engine.accept_score("ana", "ben") < 0
    assert not village.engine.request("ana", "ben")
    assert village.engine.accept_score("cal", "dot") > 0
    assert village.engine.request("cal", "dot")


async def test_the_whole_conversation_is_one_call_and_plays_line_by_line() -> None:
    village = Village(relationships=friends(ANA, BEN))
    village.engine.start("ana", "ben")

    await village.run()

    [ended] = village.ended
    conversation = ended.conversation
    assert [(line.speaker, line.text) for line in conversation.lines] == [
        ("ana", "Morning, Ben!"),
        ("ben", "Morning. Lovely day."),
        ("ana", "It is. Right, I'll let you get on."),
        ("ben", "Bye then."),
    ]
    assert conversation.lines == village.spoken
    [(asked, request)] = village.script.calls
    assert asked < START + timedelta(seconds=0.5)
    assert request.model == "claude-haiku-4-5"
    assert [record.purpose for record in village.records] == ["conversation"]
    last = village.spoken[-1]
    assert conversation.ended == last.timestamp + timedelta(seconds=last.duration)
    assert village.engine.live() == []
    assert not any(mind.paused for mind in village.behaviour.minds.values())
    cooldown = conversation.ended + timedelta(minutes=DEFAULT_CONFIG.cooldown)
    assert village.behaviour.minds["ana"].cooldowns["ben"] == cooldown
    assert village.behaviour.minds["ben"].cooldowns["ana"] == cooldown


async def test_lines_take_as_long_as_saying_them_with_a_gap_between() -> None:
    lines = ["One two three four five."] * 4
    village = Village([script(*lines), ""])
    village.engine.start("ana", "ben")

    await village.run(minutes=1)

    spoken = village.spoken
    assert [line.speaker for line in spoken] == ["ana", "ben", "ana", "ben"]
    assert spoken[0].timestamp < START + timedelta(seconds=2)
    assert {line.duration for line in spoken} == {1.5}
    for line, after in itertools.pairwise(spoken):
        assert after.timestamp == line.timestamp + timedelta(seconds=1.5 + 0.5)


async def test_a_measured_voice_paces_its_speakers_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    rate = SpeakingRate(base_seconds=0.4, seconds_per_word=0.26)
    monkeypatch.setattr(engine, "speaking_rate", lambda npc: rate if npc == "ana" else None)
    village = Village([script("One two three four five.", "Six seven eight nine ten."), ""])
    village.engine.start("ana", "ben")

    await village.run(minutes=1)

    ana, ben = village.spoken
    assert (ana.duration, ben.duration) == (1.7, 1.5)
    assert ben.timestamp == ana.timestamp + timedelta(seconds=1.7 + 0.5)


async def test_a_line_past_max_words_is_cut_at_a_sentence() -> None:
    village = Village(
        [script("One two three four. Five six seven. Eight nine.", "Bye now.")],
        config=ConversationConfig(max_words=5),
    )
    village.engine.start("ana", "ben")

    await village.run(minutes=0.2)

    assert village.spoken[0].text == "One two three four. Five six seven."


async def test_each_line_is_drafted_one_ahead_of_being_spoken() -> None:
    village = Village()
    village.engine.start("ana", "ben")

    await village.run(minutes=1)

    order = [
        (type(event).__name__, event.line.id)
        for event in village.events
        if isinstance(event, LineDrafted | LineSpoken)
    ]
    assert order == [
        ("LineDrafted", 1),
        ("LineSpoken", 1),
        ("LineDrafted", 2),
        ("LineSpoken", 2),
        ("LineDrafted", 3),
        ("LineSpoken", 3),
        ("LineDrafted", 4),
        ("LineSpoken", 4),
    ]
    spoken = village.spoken
    for line, drafted in zip(spoken, village.drafted[1:], strict=False):
        assert drafted.timestamp == line.timestamp + timedelta(seconds=line.duration + 0.5)
    assert [line.text for line in village.drafted] == [line.text for line in spoken]


async def test_the_first_line_plays_while_the_rest_is_still_streaming() -> None:
    more = asyncio.Event()
    first, rest = CHAT.split("\n", 1)
    village = Village(provider=FakeProvider([[first + "\n", more, rest]]))

    class Release:
        def tick(self, dt: float) -> None:
            if village.clock.now >= START + timedelta(seconds=20):
                more.set()

    village.world.loop.register(Release())
    village.engine.start("ana", "ben")
    await village.run(minutes=1)

    lines = village.spoken
    assert lines[0].text == "Morning, Ben!" and lines[0].timestamp < START + timedelta(seconds=1)
    assert lines[1].timestamp >= START + timedelta(seconds=20)
    assert len(lines) == 4


async def test_a_stream_that_breaks_mid_line_ends_at_the_last_complete_line() -> None:
    first, second, *_ = CHAT.split("\n")
    broken = [f"{first}\n", f"{second}\n", "Ana: It is. Right, I'll", LLMError("cut short")]
    village = Village(provider=FakeProvider([broken]))
    village.engine.start("ana", "ben")

    await village.run()

    [ended] = village.ended
    assert [line.text for line in ended.conversation.lines] == [
        "Morning, Ben!",
        "Morning. Lovely day.",
    ]
    last = ended.conversation.lines[-1]
    assert ended.conversation.ended == last.timestamp + timedelta(seconds=last.duration)
    assert [record.error for record in village.records] == ["LLMError: cut short"]
    assert not any(mind.paused for mind in village.behaviour.minds.values())


@pytest.mark.parametrize(
    "reply",
    [LLMError("usage limit reached"), ["Ana: Morning, B", LLMError("cut short")], ""],
)
async def test_a_script_that_never_gets_to_a_line_ends_before_anyone_speaks(
    reply: object,
) -> None:
    village = Village(provider=FakeProvider([reply]))  # type: ignore[list-item]
    village.engine.start("ana", "ben")

    await village.run(minutes=0.2)

    [ended] = village.ended
    assert ended.conversation.lines == []
    assert village.spoken == [] and village.drafted == []
    assert not village.engine.talking("ana") and not village.engine.talking("ben")
    assert not any(mind.paused for mind in village.behaviour.minds.values())


async def test_a_script_that_stops_well_short_gets_one_call_for_the_rest() -> None:
    replies = [
        script("Morning, Ben!", "Morning."),
        "Ana: Lovely day for it. [values: connection]",
        "Ben: It is. [values: connection]",
    ]
    village = Village(replies)
    village.engine.start("ana", "ben")

    await village.run()

    [ended] = village.ended
    assert [(line.speaker, line.text) for line in ended.conversation.lines] == [
        ("ana", "Morning, Ben!"),
        ("ben", "Morning."),
        ("ana", "Lovely day for it."),
    ]
    first, more = village.script.prompts
    assert "## The scene so far\nAna: Morning, Ben!\nBen: Morning.\n\nWrite the rest" in more
    assert "If it has already ended, write nothing." in more
    assert more.startswith(first)


async def test_a_script_past_half_its_plan_isnt_continued_whatever_its_last_line() -> None:
    village = Village(["", ""])
    village.engine.start("ana", "ben")
    half = -(-village.scene().plan.length // 2)
    village.script.replies = itertools.cycle([script(*["Nice day."] * (half - 1), "Ta-ra, then.")])

    await village.run()

    assert len(village.script.calls) == 1
    assert village.ended[0].conversation.lines[-1].text == "Ta-ra, then."


async def test_a_reply_without_names_adds_nothing() -> None:
    village = Village([script("Morning, Ben!", "Morning."), "The scene has ended."])
    village.engine.start("ana", "ben")

    await village.run()

    assert len(village.script.calls) == 2
    assert [line.text for line in village.ended[0].conversation.lines] == [
        "Morning, Ben!",
        "Morning.",
    ]


async def test_a_script_that_says_goodbye_early_isnt_continued() -> None:
    village = Village([script("Morning! Can't stop, see you later.", "Bye!")])
    village.engine.start("ana", "ben")

    await village.run()

    assert len(village.script.calls) == 1
    assert [line.text for line in village.ended[0].conversation.lines] == [
        "Morning! Can't stop, see you later.",
        "Bye!",
    ]


async def test_a_script_longer_than_max_lines_is_cut_there() -> None:
    village = Village(
        [script(*[f"Line {n}." for n in range(10)])],
        config=ConversationConfig(max_lines=6),
    )
    village.engine.start("ana", "ben")

    await village.run()

    assert len(village.ended[0].conversation.lines) == 6


class Audio:
    """What I1 would say about each NPC line's audio: made when `make` says, played from the
    line's start."""

    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self.made: dict[int, float] = {}

    def make(self, seconds: float) -> Callable[[LineDrafted | LineSpoken], None]:
        def record(event: LineDrafted | LineSpoken) -> None:
            if event.line.speaker != PLAYER_ID:
                self.made.setdefault(event.line.id, seconds)

        return record

    def duration(self, line: Line) -> float | None:
        return self.made.get(line.id)

    def remaining(self, line: Line) -> float | None:
        if line.speaker == PLAYER_ID:
            return 0.0
        if line.id not in self.made:
            return None
        ends = line.timestamp + timedelta(seconds=self.made[line.id])
        return max(0.0, (ends - self.clock.now).total_seconds())


async def test_a_voiced_line_lasts_as_long_as_its_audio() -> None:
    village = Village(relationships=friends(ANA, BEN))
    village.engine.audio = audio = Audio(village.clock)
    village.world.bus.subscribe(LineDrafted, audio.make(2.345))
    village.engine.start("ana", "ben")

    await village.run(minutes=1)

    lines = village.spoken
    assert len(lines) == 4
    assert {line.duration for line in lines} == {2.35}
    for line, after in itertools.pairwise(lines):
        assert after.timestamp == line.timestamp + timedelta(seconds=2.35 + 0.5)


async def test_the_next_line_waits_for_audio_that_runs_longer_than_its_line() -> None:
    village = Village(relationships=friends(ANA, BEN))
    village.engine.audio = audio = Audio(village.clock)
    village.world.bus.subscribe(LineSpoken, audio.make(4.0))
    village.engine.start("ana", "ben")

    await village.run(minutes=1)

    first, second, *_ = village.spoken
    assert first.duration == 1.0
    assert second.timestamp == first.timestamp + timedelta(seconds=4.0 + 0.5)


async def test_the_next_line_waits_a_while_for_audio_still_being_made() -> None:
    village = Village(relationships=friends(ANA, BEN), config=ConversationConfig(voice_wait=2))
    village.engine.audio = Audio(village.clock)
    village.engine.start("ana", "ben")

    await village.run(minutes=1)

    first, second, *_ = village.spoken
    first_ends = first.timestamp + timedelta(seconds=first.duration)
    assert first_ends + timedelta(seconds=2) <= second.timestamp
    assert second.timestamp <= first_ends + timedelta(seconds=2 + 0.1 + 0.5)


LONG_CHAT = script(*[f"Line number {n}, all about the weather." for n in range(1, 9)])


async def test_an_urgent_need_cuts_it_short_and_b3_hears_only_what_was_said() -> None:
    provider = FakeProvider([LONG_CHAT, Extraction(reflections=[])])
    village = Village(provider=provider)
    reflector = Reflector(village.store, lambda: village.behaviour.npcs, lambda: village.llm)
    village.world.bus.subscribe(ConversationEnded, reflector.on_ended)
    village.engine.start("ana", "ben")
    await village.run_until(lambda: len(village.spoken) == 2)

    village.behaviour.minds["ben"].needs[Need.REST] = 0.99
    await village.run()
    await asyncio.gather(*reflector.tasks)

    [ended] = village.ended
    lines = ended.conversation.lines
    assert [line.text for line in lines[:2]] == [
        "Line number 1, all about the weather.",
        "Line number 2, all about the weather.",
    ]
    goodbye = lines[2]
    assert len(lines) == 3
    assert (goodbye.speaker, goodbye.text) == ("ben", GOODBYES[Need.REST][0].format(name="Ana"))
    assert goodbye.timestamp == lines[1].timestamp + timedelta(seconds=lines[1].duration + 0.5)
    assert ended.conversation.ended == goodbye.timestamp + timedelta(seconds=goodbye.duration)
    unspoken = [line for line in village.drafted if line not in lines]
    assert [line.text for line in unspoken] == ["Line number 3, all about the weather."]
    reflecting = provider.requests[1].messages[-1].content
    assert "Line number 2, all about the weather." in reflecting
    assert goodbye.text in reflecting
    assert "Line number 3" not in reflecting


async def test_a_need_that_was_already_urgent_doesnt_cut_it_short() -> None:
    village = Village()
    village.behaviour.minds["ben"].needs[Need.NEWS] = 0.99
    village.engine.start("ana", "ben")

    await village.run()

    assert len(village.ended[0].conversation.lines) == 4


async def test_someone_pulled_away_mid_line_lets_it_finish_then_says_goodbye() -> None:
    village = Village([LONG_CHAT])
    village.engine.start("ana", "ben")
    await village.run_until(lambda: len(village.spoken) == 1)
    first = village.spoken[0]

    free = village.engine.cut("ana", "player")
    assert village.engine.state("ana")["leaving"] is True
    await village.run()

    [ended] = village.ended
    first, goodbye = ended.conversation.lines
    assert goodbye.speaker == "ana"
    assert goodbye.text in [text.format(name="Ben") for text in GOODBYES["player"]]
    assert goodbye.timestamp == first.timestamp + timedelta(seconds=first.duration + 0.5)
    assert free == goodbye.timestamp + timedelta(seconds=goodbye.duration)


async def test_no_goodbye_after_one_has_been_said() -> None:
    village = Village([script("Morning! Can't stop, see you later.", "Bye!", "What?")])
    village.engine.start("ana", "ben")
    await village.run_until(lambda: len(village.spoken) == 1)

    village.engine.cut("ana", "player")
    await village.run()

    assert [line.text for line in village.ended[0].conversation.lines] == [
        "Morning! Can't stop, see you later."
    ]


async def test_pulled_away_after_the_other_said_goodbye_gets_a_short_one_back() -> None:
    village = Village([script("Morning! Can't stop, see you later.", "Bye!", "What?")])
    village.engine.start("ana", "ben")
    await village.run_until(lambda: len(village.spoken) == 1)

    village.engine.cut("ben", Need.REST)
    await village.run()

    _, goodbye = village.ended[0].conversation.lines
    assert (goodbye.speaker, goodbye.text) in [("ben", "Bye, Ana."), ("ben", "See you, Ana.")]


async def test_pulled_away_before_anyone_spoke_it_never_starts() -> None:
    hang = asyncio.Event()
    village = Village(provider=FakeProvider([["Ana: Morn", hang]]))
    village.engine.start("ana", "ben")
    await village.run(minutes=0.1)

    assert village.engine.cut("ben", "player") == village.clock.now
    await asyncio.sleep(0)

    [ended] = village.ended
    assert ended.conversation.lines == []
    assert [record.error for record in village.records] == ["cancelled"]
    assert village.engine.cut("ben", "player") is None


async def test_the_prompt_brings_in_both_sides_and_what_is_between_them(
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

    [(_, request)] = village.script.calls
    prompt = request.messages[-1].content
    assert "You write the dialogue" in request.system
    assert prompt.startswith("It's 10:00, at The Daily Grind. Ana has just walked up to Ben.")
    ana, ben, between, direction = prompt.split("\n\n## ")[1:]
    assert ana.startswith("Ana\nAna Test, aged")
    assert ANA.persona in ana and f"How Ana speaks: {ANA.speaking_style}" in ana
    assert "Ana likes Ben a lot" in ana and "Ana knows them well." in ana
    assert "On Ana's mind, which only Ana knows:\n- Ben lent me his ladder." in ana
    assert "News Ana read and might bring up:\n- ana read that octopuses dream." in ana
    assert ben.startswith("Ben\n") and "Ben barely knows them." in ben
    assert "ladder" not in ben and "- ben read that octopuses dream." in ben
    assert between == "Between them\n- 2 days ago, Ben: fixed her bike"
    assert direction.startswith("Direction\n- Ana is ")
    assert "Ana speaks first." in direction


async def test_a_secret_stays_with_whoever_was_told_it() -> None:
    village = Village(npcs=(ANA, BEN, CAL))
    secret = "they're selling the bakery"
    told = Flag(
        id="s1", kind=FlagKind.SECRET, owner="ana", about="cal", description=secret, created=START
    )
    village.store.add(
        feeling(ANA, "cal").model_copy(update={"flags": [told]}),
        Memory(
            owner="ana",
            kind=MemoryKind.CONVERSATION,
            content="Cal swore me to secrecy about the bakery.",
            salience=0.9,
            valence=-0.2,
            timestamp=START - timedelta(hours=1),
            about=["cal"],
        ),
    )
    village.engine.start("ana", "ben")

    await village.run(minutes=0.1)

    [(_, request)] = village.script.calls
    ana, ben, *_ = request.messages[-1].content.split("\n\n## ")[1:]
    assert f"Told to Ana in confidence, which only Ana knows:\n- Cal: {secret}" in ana
    assert "On Ana's mind, which only Ana knows:\n- Cal swore me to secrecy" in ana
    assert "bakery" not in ben
    assert "Neither mentions what only the other knows" in request.system
    assert "what someone was told in confidence stays with them" in request.system


async def test_without_news_reactions_there_are_no_topics(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "simile.news.reactions", None)
    village = Village(relationships=friends(ANA, BEN))
    village.engine.start("ana", "ben")

    await village.run(minutes=0.1)

    assert "News" not in village.script.prompts[0]


async def test_friends_get_a_longer_scene_than_a_pair_who_dislike_each_other() -> None:
    enemies = [feeling(ANA, "ben", like=0.15), feeling(BEN, "ana", like=0.15)]
    lengths = []
    for relationships in (enemies, friends(ANA, BEN)):
        village = Village(relationships=relationships)
        village.engine.start("ana", "ben")
        lengths.append(village.scene().plan.length)

    assert DEFAULT_CONFIG.min_lines + 2 <= lengths[0] < lengths[1]


async def test_line_ids_are_unique_across_conversations() -> None:
    chat = "".join(
        f"{name}: Hello. [values: connection]\n" for name in ["Ana", "Ben", "Cal", "Dot"]
    )
    village = Village(
        [chat], npcs=(ANA, BEN, CAL, DOT), relationships=[*friends(ANA, BEN), *friends(CAL, DOT)]
    )
    village.engine.start("ana", "ben")
    village.engine.start("cal", "dot")

    await village.run(minutes=1)

    ids = [line.id for line in village.spoken]
    assert len({line.conversation_id for line in village.spoken}) == 2
    assert len(ids) == len(set(ids))


async def test_finished_conversations_stay_reachable() -> None:
    village = Village()
    started = village.engine.start("ana", "ben")

    await village.run()

    finished = village.engine.conversation(started.id)
    assert finished is not None
    assert finished == village.ended[0].conversation
    assert finished.lines == village.spoken
    assert village.engine.state("ana") == {"conversation": None}
    assert village.engine.conversation("nope") is None


async def test_closing_stops_writing() -> None:
    hang = asyncio.Event()
    provider = FakeProvider([["Ana: Well", hang]])
    village = Village(provider=provider)
    village.engine.start("ana", "ben")
    await village.run(minutes=0.1)

    assert provider.requests
    assert village.records == []

    await asyncio.wait_for(village.engine.close(), 1)

    assert village.spoken == []
    assert [record.error for record in village.records] == ["cancelled"]


async def test_a_first_line_that_takes_too_long_is_asked_for_once_more() -> None:
    hang = asyncio.Event()
    provider = FakeProvider([["Ana: Well", hang], CHAT])
    village = Village(config=ConversationConfig(first_line_timeout=0.05), provider=provider)
    village.engine.start("ana", "ben")

    for _ in range(3):
        await village.run(minutes=0.1)
        await asyncio.sleep(0.1)
    await village.run()

    [ended] = village.ended
    assert len(ended.conversation.lines) == 4
    assert [record.error for record in village.records] == ["cancelled", None]


async def test_a_second_slow_first_line_ends_it_before_anyone_speaks() -> None:
    hang = asyncio.Event()
    provider = FakeProvider([["Ana: Well", hang], ["Ana: Um", hang]])
    village = Village(config=ConversationConfig(first_line_timeout=0.05), provider=provider)
    village.engine.start("ana", "ben")

    for _ in range(3):
        await village.run(minutes=0.1)
        await asyncio.sleep(0.1)

    [ended] = village.ended
    assert ended.conversation.lines == []
    assert [record.error for record in village.records] == ["cancelled", "cancelled"]
    assert not any(mind.paused for mind in village.behaviour.minds.values())


async def test_a_cut_while_the_script_streams_drops_the_rest() -> None:
    more = asyncio.Event()
    first, rest = LONG_CHAT.split("\n", 1)
    village = Village(provider=FakeProvider([[first + "\n", more, rest]]))
    village.engine.start("ana", "ben")
    await village.run_until(lambda: len(village.spoken) == 1)

    village.engine.cut("ben", "player")
    more.set()
    await village.run()

    [ended] = village.ended
    said, goodbye = ended.conversation.lines
    assert said.text == "Line number 1, all about the weather."
    assert goodbye.speaker == "ben"
    assert [line.text for line in village.drafted] == [said.text, goodbye.text]
    assert [record.error for record in village.records] == ["cancelled"]


async def test_a_script_that_stalls_times_out_and_frees_its_slot() -> None:
    never = asyncio.Event()
    first = CHAT.split("\n")[0] + "\n"
    provider = FakeProvider([[first, never], "Free again."])
    village = Village(config=ConversationConfig(line_timeout=0.05), provider=provider)
    village.llm = LLMClient(provider, max_concurrency=1, listeners=[village.records.append])
    village.engine.start("ana", "ben")

    await village.run(minutes=0.1)
    await asyncio.sleep(0.1)
    await village.run(minutes=0.1)

    [ended] = village.ended
    assert [line.text for line in ended.conversation.lines] == ["Morning, Ben!"]
    assert [record.error for record in village.records] == ["cancelled"]
    assert village.engine.live() == []
    assert not any(mind.paused for mind in village.behaviour.minds.values())
    assert await asyncio.wait_for(village.llm.complete("Still there?"), 1) == "Free again."


RED_PLANET = work("cal-1", "cal", "Red Planet", START - timedelta(hours=3), tags=["mars"])
SAW_IT = 'I saw Cal Test\'s mural "Red Planet" on the tower. Brave stuff.'


def sides(prompt: str) -> tuple[str, str]:
    a, b, *_ = prompt.split("\n\n## ")[1:]
    return a, b


async def test_a_mural_someone_saw_is_theirs_to_bring_up_once() -> None:
    village = Village(npcs=(ANA, BEN, CAL))
    village.engine.work = {RED_PLANET.id: RED_PLANET}.get
    village.store.add(remembers("ana", RED_PLANET, SAW_IT, START - timedelta(hours=1)))
    village.engine.start("ana", "ben")

    await village.run(minutes=0.1)

    prompt = village.script.prompts[0]
    ana, ben = sides(prompt)
    assert f"Works by others Ana might bring up, which only Ana knows:\n- {SAW_IT}" in ana
    assert "Red Planet" not in ben
    assert prompt.count("Red Planet") == 1


async def test_talking_to_the_artist_both_know_whose_work_it_is() -> None:
    village = Village(npcs=(ANA, CAL))
    village.engine.work = {RED_PLANET.id: RED_PLANET}.get
    painted = 'I painted "Red Planet" on the tower. Mars is for everyone.'
    village.store.add(
        remembers("ana", RED_PLANET, SAW_IT, START - timedelta(hours=1)),
        remembers("cal", RED_PLANET, painted, START - timedelta(days=5), salience=0.6),
    )
    village.engine.start("ana", "cal")

    await village.run(minutes=0.1)

    prompt = village.script.prompts[0]
    ana, cal = sides(prompt)
    assert f"- {SAW_IT} (Cal made it.)" in ana
    assert (
        f"Cal's own works, which Cal might bring up and stand by, in notes only Cal knows:\n"
        f"- {painted}" in cal
    )
    assert "Brave stuff" not in cal
    assert prompt.count(painted) == 1


async def test_whoever_painted_over_your_mural_reminds_you_of_it() -> None:
    gulls = work("ben-1", "ben", "Gulls", START - timedelta(days=1))
    over = work("ana-1", "ana", "Red Planet", START - timedelta(hours=2))
    covered = 'Ana Test has painted "Red Planet" over my mural "Gulls" on the tower. Rude.'
    painted = 'I painted "Red Planet" on the tower over Ben Test\'s "Gulls". Bold.'
    village = Village(npcs=(ANA, BEN, DOT), config=ConversationConfig(works=1))
    village.engine.work = {w.id: w for w in (gulls, over, RED_PLANET)}.get
    village.store.add(
        remembers("ben", over, covered, START - timedelta(hours=2), salience=0.7),
        remembers("ben", RED_PLANET, SAW_IT, START, salience=0.9),
        remembers("ana", over, painted, START - timedelta(days=5), salience=0.6),
    )
    prompts = []
    for other in ("ana", "dot"):
        village.engine.start("ben", other)
        prompts.append(village.scene().prompt)
        village.engine.end(village.scene().conversation.id)

    works = "Works by others Ben might bring up, which only Ben knows:\n- "
    ben, ana = sides(prompts[0])
    assert ben.endswith(f"{works}{covered} (Ana made it.)")
    assert (
        f"Ana's own works, which Ana might bring up and stand by, in notes only Ana knows:\n"
        f"- {painted}" in ana
    )
    ben, _ = sides(prompts[1])
    assert ben.endswith(f"{works}{SAW_IT}")


async def test_faded_and_lost_works_and_the_players_memories_arent_raised() -> None:
    lost = work("cal-2", "cal", "Gone", START)
    village = Village(npcs=(ANA, BEN, CAL))
    village.engine.work = {RED_PLANET.id: RED_PLANET}.get
    village.store.add(
        remembers("ana", RED_PLANET, SAW_IT, START - timedelta(days=5), salience=0.6),
        remembers("ana", lost, "I saw Cal Test's mural Gone.", START),
        remembers(PLAYER_ID, RED_PLANET, SAW_IT, START),
    )
    village.engine.start("ana", "ben")

    await village.run(minutes=0.1)

    assert "Works by others" not in village.script.prompts[0]


async def test_what_a_work_is_about_makes_them_keener() -> None:
    justice = work("cal-3", "cal", "Fair Shares", START, values={CoreValue.JUSTICE: 1.0})
    keen = []
    for memories in ((), (remembers("ana", justice, "I saw Fair Shares. Yes!", START),)):
        village = Village(npcs=(ANA, BEN, CAL))
        village.engine.work = {justice.id: justice}.get
        village.store.add(*memories)
        village.engine.start("ana", "ben")
        keen.append(village.scene().plan.stances["ana"].keen)

    assert keen[1] > keen[0]
