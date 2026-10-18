import asyncio
import itertools
import re
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
    player,
    system_prompt,
)
from simile.conversation.engine import GOODBYES, PLAYER
from simile.conversation.player import (
    DEFAULT_PLAYER_CONFIG,
    TURNED_AWAY,
    PlayerConfig,
    PlayerConversations,
    Sentences,
    came_up,
    says_goodbye,
    split,
)
from simile.conversation.prompt import Cue, WorkTopic
from simile.llm import CallRecord, FakeProvider, LLMClient, LLMError, Request
from simile.memory import MemoryStore
from simile.npc import load_npcs
from simile.reflection import Deed, Extraction, Reflection, Reflector
from simile.schema import (
    PLAYER_ID,
    VILLAGE_MAP,
    Aspect,
    CoreValue,
    InteractionEvent,
    Line,
    Medium,
    Memory,
    MemoryKind,
    Npc,
    Relationship,
    Work,
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
from simile.social import describe, meet
from simile.voice import SpeakingRate
from simile.world import Movement, Point
from simile.world.map import load_maps

from .conftest import remembers, work

pytestmark = pytest.mark.anyio

MAPS = load_maps()
START = datetime(2026, 1, 1, 10, tzinfo=UTC)
TEMPLATE = load_npcs()[0]


def make_npc(id: str, home: str, **values: float) -> Npc:
    scores = {value: values.get(value.value, 0.5) for value in CoreValue}
    return TEMPLATE.model_copy(
        update={"id": id, "name": f"{id.title()} Test", "home": home, "values": scores}
    )


ANA = make_npc("ana", "house_1", connection=1.0, justice=1.0, tradition=0.0)
BEN = make_npc("ben", "house_2", connection=0.0, independence=1.0, peace_of_mind=1.0)
CAL = make_npc("cal", "house_3")


def feeling(owner: Npc, about: str, **scores: float) -> Relationship:
    return meet(owner, about).model_copy(update=scores)


class Script:
    """Replies in turn, recording each request."""

    def __init__(self, replies: Sequence[str]) -> None:
        self.replies = itertools.cycle(replies)
        self.requests: list[Request] = []

    def __call__(self, request: Request) -> str:
        self.requests.append(request)
        return next(self.replies)

    @property
    def prompts(self) -> list[str]:
        return [request.messages[-1].content for request in self.requests]


class Recording(LLMClient):
    def __init__(self, provider: FakeProvider, records: list[CallRecord]) -> None:
        super().__init__(provider, listeners=[records.append])
        self.priorities: list[int] = []

    def stream(self, prompt, **kwargs):  # type: ignore[no-untyped-def,override]
        self.priorities.append(kwargs.get("priority", 0))
        return super().stream(prompt, **kwargs)


class Village:
    """NPCs at the coffee shop with the player next to the first, on a fake wall clock.
    Behaviour doesn't tick, so NPCs only go anywhere when a test moves them."""

    def __init__(
        self,
        replies: Sequence[str] = ("Lovely to meet you. Settling in? [values: connection]",),
        *,
        npcs: Sequence[Npc] = (ANA, BEN),
        relationships: Sequence[Relationship] = (),
        config: ConversationConfig = DEFAULT_CONFIG,
        player: PlayerConfig = DEFAULT_PLAYER_CONFIG,
        provider: FakeProvider | None = None,
    ) -> None:
        self.world = World(Clock(START), FakeWallClock())
        self.store = MemoryStore(":memory:")
        self.store.add(*relationships)
        self.movement = Movement(MAPS, self.world.bus)
        for npc in npcs:
            self.movement.place(npc.id, "coffee_shop")
        self.behaviour = Behaviour(
            self.world.clock, self.world.bus, self.movement, npcs, self.store, seed=0
        )
        self.behaviour.start()
        for mind in self.behaviour.minds.values():
            mind.goal = Goal(Activity.IDLE)
        self.walk_to(npcs[0].id, 1)
        self.script = Script(replies)
        self.provider = provider or FakeProvider(itertools.repeat(self.script, 100))
        self.records: list[CallRecord] = []
        self.llm = Recording(self.provider, self.records)
        self.engine = ConversationEngine(
            self.clock, self.world.bus, self.behaviour, self.store, lambda: self.llm, config=config
        )
        self.connected = True
        self.players = PlayerConversations(
            self.engine, connected=lambda: self.connected, config=player, seed=0
        )
        self.engine.player_request = self.players.request
        self.events: list[Event] = []
        self.world.bus.subscribe(Event, self.events.append)
        self.world.loop.register(self.engine)
        self.world.loop.register(self.players)

    @property
    def clock(self) -> Clock:
        return self.world.clock

    def walk_to(self, npc: str, tiles: float) -> None:
        """Put the player `tiles` to the right of `npc`."""
        here = self.movement.position(npc)
        self.movement.track(PLAYER_ID, Point(here.x + tiles, here.y, here.map))

    async def run(self, seconds: float = 5) -> None:
        await self.world.loop.run(timedelta(seconds=seconds))

    def of[E: Event](self, kind: type[E]) -> list[E]:
        return [event for event in self.events if isinstance(event, kind)]

    @property
    def spoken(self) -> list[Line]:
        return [event.line for event in self.of(LineSpoken)]

    def said(self, speaker: str) -> list[str]:
        return [line.text for line in self.spoken if line.speaker == speaker]

    @property
    def ended(self) -> list[ConversationEnded]:
        return self.of(ConversationEnded)


async def test_the_player_talks_and_the_npc_replies_a_sentence_at_a_time() -> None:
    village = Village()

    heard = village.players.say("  Hi, I'm new  here. ", "ana")
    await village.run()

    [started] = village.of(ConversationStarted)
    assert started.conversation.participants == [PLAYER_ID, "ana"]
    assert heard is not None and heard.text == "Hi, I'm new here."
    player, *reply = village.spoken
    assert player == heard
    assert [line.text for line in reply] == ["Lovely to meet you.", "Settling in?"]
    assert {line.speaker for line in reply} == {"ana"}
    first, second = reply
    assert second.timestamp == first.timestamp + timedelta(seconds=first.duration)
    drafted = [event.line for event in village.of(LineDrafted)]
    assert drafted == reply
    assert village.behaviour.goal("ana") == Goal(Activity.TALK, PLAYER_ID)
    assert village.of(Facing) == [Facing("ana", PLAYER_ID, "right")]
    [live] = village.engine.live()
    assert live.lines == village.spoken
    assert village.engine.talking(PLAYER_ID) and village.engine.talking("ana")
    assert village.engine.state("ana")["talking_to"] == PLAYER_ID


async def test_a_measured_voice_paces_the_npcs_sentences(monkeypatch: pytest.MonkeyPatch) -> None:
    rate = SpeakingRate(base_seconds=0.7, seconds_per_word=0.27)
    monkeypatch.setattr(player, "speaking_rate", lambda npc: rate if npc == "ana" else None)
    village = Village()

    heard = village.players.say("Hi, I'm new here.", "ana")
    await village.run()

    assert heard is not None and heard.duration == 1.2
    _, first, second = village.spoken
    assert (first.duration, second.duration) == (1.78, 1.24)
    assert second.timestamp == first.timestamp + timedelta(seconds=1.78)


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


async def test_voiced_sentences_last_as_long_as_their_audio() -> None:
    village = Village(["One. Two. Three."])
    village.engine.audio = audio = Audio(village.clock)
    village.world.bus.subscribe(LineDrafted, audio.make(2.5))

    village.players.say("Count for me.", "ana")
    await village.run(seconds=10)

    _, one, two, three = village.spoken
    assert (one.duration, two.duration, three.duration) == (2.5, 2.5, 2.5)
    assert two.timestamp == one.timestamp + timedelta(seconds=2.5)
    assert three.timestamp == two.timestamp + timedelta(seconds=2.5)


async def test_the_next_sentence_waits_for_audio_that_runs_longer_than_its_line() -> None:
    village = Village(["One. Two."])
    village.engine.audio = audio = Audio(village.clock)
    village.world.bus.subscribe(LineSpoken, audio.make(3.0))

    village.players.say("Count for me.", "ana")
    await village.run(seconds=10)

    _, one, two = village.spoken
    assert one.duration == 1.0
    assert two.timestamp == one.timestamp + timedelta(seconds=3.0)


async def test_the_first_sentence_is_out_before_the_rest_is_written() -> None:
    rest = asyncio.Event()
    provider = FakeProvider([["Oh, hello! ", "Welcome to ", rest, "the village.\n[values: x]"]])
    village = Village(provider=provider)

    village.players.say("Hello", "ana")
    await village.run(2)

    assert village.said("ana") == ["Oh, hello!"]
    rest.set()
    await village.run(2)
    assert village.said("ana") == ["Oh, hello!", "Welcome to the village."]


async def test_a_long_first_sentence_starts_at_its_first_clause() -> None:
    rest = asyncio.Event()
    chunks = ["Go and find Marcus at the maker space—", "he knows everyone ", "around ", rest]
    provider = FakeProvider([[*chunks, "here.\n[values: x]"]])
    village = Village(provider=provider)

    village.players.say("Who should I meet?", "ana")
    await village.run(2)

    assert village.said("ana") == ["Go and find Marcus at the maker space—"]
    rest.set()
    await village.run(4)
    assert village.said("ana") == [
        "Go and find Marcus at the maker space—",
        "he knows everyone around here.",
    ]


async def test_a_sentence_written_late_still_waits_for_the_audio_before_it() -> None:
    rest = asyncio.Event()
    provider = FakeProvider([["Oh, hello! ", "Welcome to ", rest, "the village.\n[values: x]"]])
    village = Village(provider=provider)
    village.engine.audio = audio = Audio(village.clock)
    village.world.bus.subscribe(LineSpoken, audio.make(3.0))

    village.players.say("Hello", "ana")
    await village.run(2)
    rest.set()
    await village.run(3)

    _, hello, welcome = village.spoken
    assert hello.duration == 1.0
    assert welcome.timestamp == hello.timestamp + timedelta(seconds=3.0)


async def test_the_reply_is_written_from_the_npcs_side_at_player_priority() -> None:
    village = Village()

    village.players.say("Hi there.", "ana")
    await village.run()

    [request] = village.script.requests
    prompt = request.messages[-1].content
    assert ANA.persona in request.system
    assert "You're with Visitor (a newcomer to the village)." in prompt
    assert describe(meet(ANA, PLAYER_ID), "Visitor") in prompt
    assert "The conversation so far:\nVisitor: Hi there." in prompt
    assert prompt.endswith(
        "Say your next line to Visitor. Keep the conversation going: don't wrap it up or say "
        "goodbye yet."
    )
    assert village.llm.priorities == [1]
    assert [record.purpose for record in village.records] == ["player-reply"]


async def test_what_b3_takes_from_a_conversation_comes_up_in_the_next() -> None:
    remembered = Reflection(
        npc="ana",
        summary="Visitor told me they keep bees on their balcony.",
        valence=0.6,
        salience=0.8,
        events=[
            Deed(
                by=PLAYER_ID,
                action="told Ana about their bees",
                aspects=[Aspect.LIKE],
                valence=0.6,
                magnitude=0.5,
            )
        ],
    )
    provider = FakeProvider(
        [
            "Bees! How lovely. [values: connection]",
            "Bye now!",
            Extraction(reflections=[remembered]),
            "Hello again! How are the bees?",
        ]
    )
    village = Village(provider=provider)
    reflector = Reflector(village.store, lambda: village.behaviour.npcs, lambda: village.llm)
    village.world.bus.subscribe(ConversationEnded, reflector.on_ended)

    village.players.say("I keep bees on my balcony.", "ana")
    await village.run(4)
    village.players.say("Anyway, bye!", "ana")
    await village.run(4)
    await asyncio.gather(*reflector.tasks)
    village.players.say("Hi again!", "ana")
    await village.run(2)

    reflection, later = provider.requests[2].messages[-1].content, provider.requests[3]
    assert "Visitor: I keep bees on my balcony." in reflection
    prompt = later.messages[-1].content
    assert "- Visitor told me they keep bees on their balcony." in prompt
    assert "- just now, Visitor: told Ana about their bees" in prompt
    assert village.said("ana")[-2:] == ["Hello again!", "How are the bees?"]


async def test_the_npc_remembers_the_player() -> None:
    village = Village(relationships=[feeling(ANA, PLAYER_ID, like=0.9, familiarity=0.8)])
    village.store.add(
        Memory(
            owner="ana",
            kind=MemoryKind.CONVERSATION,
            content="Visitor asked where to buy a bike.",
            salience=0.7,
            valence=0.3,
            timestamp=START - timedelta(hours=3),
            about=[PLAYER_ID],
        ),
        InteractionEvent(
            actor=PLAYER_ID,
            target="ana",
            action="helped her carry chairs",
            aspects=[Aspect.LIKE],
            valence=0.6,
            magnitude=0.5,
            timestamp=START - timedelta(days=1),
        ),
    )

    village.players.say("Me again!", "ana")
    await village.run(1)

    prompt = village.script.prompts[0]
    assert "You like Visitor a lot" in prompt
    assert "You know them well." in prompt
    assert "- yesterday, Visitor: helped her carry chairs" in prompt
    assert "- Visitor asked where to buy a bike." in prompt


def read(owner: str, news_id: str, content: str, *topics: str) -> Memory:
    return Memory(
        owner=owner,
        kind=MemoryKind.NEWS,
        content=content,
        salience=0.6,
        valence=0.4,
        timestamp=START - timedelta(hours=1),
        topics=list(topics),
        news_id=news_id,
    )


MARS = read("ana", "mars", 'I read "Colonising Mars by 2050". I\'d paint the domes.', "space")
BARRIER = 'I read "Tidal barrier for the river". About time.'


RECALLED = f"You read about what Visitor just mentioned:\n- {BARRIER}\n\n"


async def requests_with(*memories: Memory) -> list[Request]:
    village = Village()
    village.store.add(*memories)
    village.players.say("Hi!", "ana")
    await village.run(1)
    village.players.say("Did you hear about the tidal barrier?", "ana")
    await village.run(1)
    return village.script.requests


async def test_the_resident_raises_their_own_news_and_never_sees_the_players() -> None:
    hers = [MARS, read("ana", "barrier", BARRIER)]
    players = [read(PLAYER_ID, "barrier", BARRIER), read(PLAYER_ID, "drones", "Drones regulated")]

    requests = await requests_with(*hers, *players)

    assert requests == await requests_with(*hers)
    first, second = (request.messages[-1].content for request in requests)
    assert "News you might bring up:\n" in first
    assert '- I read "Colonising Mars by 2050". I\'d paint the domes.' in first
    assert RECALLED in second


async def test_what_stuck_comes_from_the_story_the_player_names_or_else_her_own() -> None:
    mars = MARS.model_copy(update={"points": ["The domes are glass."]})
    barrier = read("ana", "barrier", BARRIER).model_copy(
        update={"points": ["It cost forty million."], "salience": 0.3}
    )

    first, second = (request.messages[-1].content for request in await requests_with(mars, barrier))

    assert 'What stuck with you from "Colonising Mars by 2050":\n- The domes are glass.' in first
    assert 'What stuck with you from "Tidal barrier for the river":\n- It cost forty million.' in (
        second
    )
    assert [first.count("What stuck with"), second.count("What stuck with")] == [1, 1]
    assert "forty million" not in first and "domes are glass" not in second


async def test_a_story_the_player_names_brings_the_residents_take_to_mind() -> None:
    village = Village()
    village.store.add(MARS, read("ana", "barrier", BARRIER, "flooding"))

    village.players.say("Did you hear about the tidal barrier?", "ana")
    await village.run(1)

    [prompt] = village.script.prompts
    assert f"Visitor: Did you hear about the tidal barrier?\n\n{RECALLED}" in prompt


@pytest.mark.parametrize(
    "said",
    [
        "Did you hear about the tidal barrier?",
        "What a lovely village this is.",
    ],
)
async def test_a_story_the_resident_didnt_read_or_one_shared_word_brings_nothing(said: str) -> None:
    village = Village()
    village.store.add(
        MARS,
        read("ana", "fete", 'I read "Village fete called off". Shame.', "community"),
        read("ben", "barrier", BARRIER),
        read(PLAYER_ID, "barrier", BARRIER),
    )

    village.players.say(said, "ana")
    await village.run(1)

    assert "You read about" not in village.script.prompts[0]


async def test_only_what_the_player_said_since_the_resident_last_spoke_counts() -> None:
    village = Village()
    village.store.add(read("ana", "barrier", BARRIER))

    village.players.say("Did you hear about the tidal barrier?", "ana")
    await village.run(1)
    village.players.say("Anyway, how's your day?", "ana")
    await village.run(1)

    first, second = village.script.prompts
    assert RECALLED in first
    assert "Visitor: Did you hear about the tidal barrier?" in second
    assert "You read about" not in second


async def test_player_lines_in_a_row_can_name_the_story_between_them() -> None:
    provider = FakeProvider([["Hmm", asyncio.Event()], "Oh, that! [values: security]"])
    village = Village(provider=provider)
    village.store.add(read("ana", "barrier", BARRIER))

    village.players.say("Did you see the tidal thing?", "ana")
    await village.run(1)
    village.players.say("The barrier, I mean.", "ana")
    await village.run(1)

    first, second = (request.messages[-1].content for request in provider.requests)
    assert "You read about" not in first
    assert f"Visitor: The barrier, I mean.\n\n{RECALLED}" in second


async def test_the_player_talks_over_the_npc() -> None:
    hang = asyncio.Event()
    provider = FakeProvider(
        [
            ["Well, ", "hello there. ", "Did you know ", hang],
            "Oh, sorry. Go on. [values: connection]",
        ]
    )
    village = Village(provider=provider)

    village.players.say("Hi!", "ana")
    await village.run(1)
    village.players.say("Wait, one thing.", "ana")
    await village.run(3)

    assert [line.text for line in village.spoken] == [
        "Hi!",
        "Well, hello there.",
        "Wait, one thing.",
        "Oh, sorry.",
        "Go on.",
    ]
    assert [record.error for record in village.records] == ["cancelled", None]
    second = provider.requests[1].messages[-1].content
    assert "Ana: Well, hello there.\nVisitor: Wait, one thing." in second


async def test_a_bored_npc_says_goodbye_and_the_conversation_ends() -> None:
    village = Village(["Hm. Right. [values: tradition]"], npcs=(BEN,))

    village.players.say("Hello!", "ben")
    await village.run(5)
    village.players.say("Lovely weather.", "ben")
    await village.run(5 + DEFAULT_PLAYER_CONFIG.farewell_wait)

    prompts = village.script.prompts
    assert len(prompts) == 2
    assert prompts[1].endswith("Wrap it up now with a brief, natural goodbye to Visitor.")
    [ended] = village.ended
    conversation = ended.conversation
    assert conversation.lines == village.spoken
    assert [line.speaker for line in conversation.lines] == [PLAYER_ID, "ben", "ben"] * 2
    last = conversation.lines[-1]
    wait = timedelta(seconds=last.duration + DEFAULT_PLAYER_CONFIG.farewell_wait)
    assert conversation.ended is not None
    assert timedelta(0) <= conversation.ended - (last.timestamp + wait) < timedelta(seconds=0.2)
    assert village.engine.live() == []
    assert not village.behaviour.minds["ben"].paused
    cooldown = village.behaviour.minds["ben"].cooldowns[PLAYER_ID]
    assert cooldown == conversation.ended + timedelta(minutes=DEFAULT_CONFIG.cooldown)


async def test_a_starving_npc_wraps_up_sooner_and_says_why() -> None:
    prompts = []
    for hunger in (0.3, 0.95):
        village = Village()
        village.behaviour.minds["ana"].needs[Need.HUNGER] = hunger
        village.players.say("Hello!", "ana")
        await village.run(5)
        village.players.say("Lovely weather.", "ana")
        await village.run(5)
        prompts.append(village.script.prompts)

    fed, starving = prompts
    assert fed[1].endswith("Keep the conversation going: don't wrap it up or say goodbye yet.")
    assert starving[1].endswith(
        "You need to get something to eat. Wrap it up now with a brief, natural goodbye to "
        "Visitor, and say why you're going."
    )
    assert all("\n\nRight now you're starving.\n\n" in prompt for prompt in starving)
    assert not any("Right now" in prompt for prompt in fed)


async def test_answering_a_goodbye_ends_it_without_another_reply() -> None:
    village = Village(["Hm. Hello. [values: tradition]", "Right, I'm off."], npcs=(BEN,))

    village.players.say("Hello!", "ben")
    await village.run(5)
    village.players.say("Hi again.", "ben")
    await village.run(4)
    village.players.say("Bye then!", "ben")

    assert len(village.script.requests) == 2
    [ended] = village.ended
    assert ended.conversation.lines[-1].text == "Bye then!"
    assert ended.conversation.ended == ended.conversation.lines[-1].timestamp


async def test_saying_goodbye_gets_one_back() -> None:
    village = Village(["Morning! [values: connection]", "Bye now, take care!"])

    village.players.say("Morning!", "ana")
    await village.run(4)
    village.players.say("I have to go. Bye!", "ana")
    await village.run(5)

    assert village.script.prompts[1].endswith("Visitor is leaving. Say a brief goodbye back.")
    [ended] = village.ended
    assert [line.text for line in ended.conversation.lines][-2:] == [
        "I have to go. Bye!",
        "Bye now, take care!",
    ]
    last = ended.conversation.lines[-1]
    assert ended.conversation.ended == last.timestamp + timedelta(seconds=last.duration)


async def test_walking_away_ends_it_at_once() -> None:
    hang = asyncio.Event()
    village = Village(provider=FakeProvider([["Well", hang]]))

    village.players.say("Hello!", "ana")
    await village.run(1)
    village.walk_to("ana", DEFAULT_PLAYER_CONFIG.leave_range + 1)
    await village.run(0.2)

    [ended] = village.ended
    assert [line.speaker for line in ended.conversation.lines] == [PLAYER_ID]
    assert [record.error for record in village.records] == ["cancelled"]
    assert not village.behaviour.minds["ana"].paused


async def test_a_player_on_another_map_has_walked_away() -> None:
    hang = asyncio.Event()
    village = Village(provider=FakeProvider([["Well", hang]]))

    village.players.say("Hello!", "ana")
    await village.run(1)
    here = village.movement.position(PLAYER_ID)
    village.movement.track(PLAYER_ID, Point(here.x, here.y, VILLAGE_MAP))
    await village.run(0.2)

    [ended] = village.ended
    assert [line.speaker for line in ended.conversation.lines] == [PLAYER_ID]
    assert not village.behaviour.minds["ana"].paused


async def test_a_disconnected_player_leaves_the_conversation() -> None:
    village = Village()
    village.players.say("Hello!", "ana")
    await village.run(4)

    village.connected = False
    await village.run(0.2)

    assert len(village.ended) == 1


async def test_a_silent_player_gets_a_goodbye() -> None:
    village = Village(["Hello! [values: connection]", "Well, I'll leave you to it."])

    village.players.say("Hi.", "ana")
    await village.run(DEFAULT_PLAYER_CONFIG.silence + DEFAULT_PLAYER_CONFIG.farewell_wait + 10)

    assert "goodbye to Visitor" in village.script.prompts[-1]
    [ended] = village.ended
    assert ended.conversation.lines[-1].text == "Well, I'll leave you to it."


async def test_a_failed_reply_ends_the_conversation() -> None:
    village = Village(provider=FakeProvider([LLMError("usage limit reached")]))

    village.players.say("Hello?", "ana")
    await village.run(1)

    [ended] = village.ended
    assert [line.speaker for line in ended.conversation.lines] == [PLAYER_ID]
    assert not village.behaviour.minds["ana"].paused


async def test_talking_to_someone_else_gets_a_goodbye_and_ends_the_first_conversation() -> None:
    village = Village()
    village.players.say("Hi Ana.", "ana")
    await village.run(4)

    village.walk_to("ben", 1)
    village.players.say("Hi Ben.", "ben")
    await village.run(6)

    first, second = village.of(ConversationStarted)
    [ended] = village.ended
    assert ended.conversation.id == first.conversation.id
    goodbye = ended.conversation.lines[-1]
    assert goodbye.speaker == "ana"
    assert goodbye.text in [text.format(name="Ben") for text in TURNED_AWAY]
    assert goodbye.timestamp == ended.conversation.ended
    assert goodbye in [event.line for event in village.of(LineDrafted)]
    order = [
        event
        for event in village.events
        if isinstance(event, ConversationStarted | ConversationEnded)
        or (isinstance(event, LineSpoken) and event.line == goodbye)
    ]
    assert order == [first, LineSpoken(goodbye), ended, second]
    assert second.conversation.participants == [PLAYER_ID, "ben"]
    assert village.said(PLAYER_ID) == ["Hi Ana.", "Hi Ben."]
    reply = next(line for line in village.spoken if line.speaker == "ben")
    assert reply.timestamp == goodbye.timestamp + timedelta(seconds=goodbye.duration)


async def test_turning_away_gets_the_goodbye_at_once_while_audio_still_plays() -> None:
    village = Village()
    village.engine.audio = audio = Audio(village.clock)
    village.world.bus.subscribe(LineSpoken, audio.make(3.0))
    village.players.say("Hi Ana.", "ana")
    await village.run(1)

    village.walk_to("ben", 1)
    turned = village.clock.now
    village.players.say("Hi Ben.", "ben")
    await village.run(6)

    [ended] = village.ended
    goodbye = ended.conversation.lines[-1]
    assert goodbye.text in [text.format(name="Ben") for text in TURNED_AWAY]
    assert goodbye.timestamp == turned


@pytest.mark.parametrize("said", [["Hi Ben.", "Got a minute?"], ["Hi.", "Ben?", "Hey!"]])
async def test_the_new_resident_waits_for_the_goodbye_however_much_the_player_says(
    said: list[str],
) -> None:
    village = Village()
    village.players.say("Hi Ana.", "ana")
    await village.run(4)

    village.walk_to("ben", 1)
    for text in said:
        village.players.say(text, "ben")
        await village.run(0.3)
    await village.run(6)

    [ended] = village.ended
    goodbye = ended.conversation.lines[-1]
    talk = village.players.talk()
    assert talk is not None
    lines = talk.conversation.lines
    assert [line.text for line in lines] == [*said, "Lovely to meet you.", "Settling in?"]
    assert lines[len(said)].timestamp == goodbye.timestamp + timedelta(seconds=goodbye.duration)


@pytest.mark.parametrize("then", ["cal", "ana"])
async def test_turning_away_again_during_the_goodbye_waits_for_it_without_another(
    then: str,
) -> None:
    village = Village(npcs=(ANA, BEN, CAL))
    village.players.say("Hi Ana.", "ana")
    await village.run(4)

    village.walk_to("ben", 1)
    village.players.say("Hi Ben.", "ben")
    await village.run(0.3)
    village.walk_to(then, 1)
    village.players.say("Oh, hello!", then)
    await village.run(6)

    to_ana, to_ben = village.ended
    assert [line.speaker for line in to_ben.conversation.lines] == [PLAYER_ID]
    goodbye = to_ana.conversation.lines[-1]
    goodbyes = {text.format(name=name) for text in TURNED_AWAY for name in ("Ben", "Cal", "Ana")}
    assert [event.line for event in village.of(LineDrafted) if event.line.text in goodbyes] == [
        goodbye
    ]
    talk = village.players.talk()
    assert talk is not None and talk.npc == then
    reply = talk.conversation.lines[1]
    assert reply.timestamp == goodbye.timestamp + timedelta(seconds=goodbye.duration)


async def test_turning_away_mid_goodbye_waits_only_for_the_sentence_being_said() -> None:
    village = Village(["Right you are, off you go. See you around! [values: connection]"])
    village.players.say("Bye, Ana!", "ana")
    await village.run(1.5)

    village.walk_to("ben", 1)
    village.players.say("Hi Ben.", "ben")
    await village.run(6)

    [ended] = village.ended
    lines = ended.conversation.lines
    assert [line.text for line in lines] == ["Bye, Ana!", "Right you are, off you go."]
    reply = next(line for line in village.spoken if line.speaker == "ben")
    assert reply.timestamp == lines[-1].timestamp + timedelta(seconds=lines[-1].duration)


async def test_turning_away_mid_reply_cuts_it_short_for_the_goodbye() -> None:
    hang = asyncio.Event()
    village = Village(provider=FakeProvider([["Well, ", hang], "Hello! [values: connection]"]))
    village.players.say("Hi Ana.", "ana")
    await village.run(1)

    village.walk_to("ben", 1)
    village.players.say("Hi Ben.", "ben")
    await village.run(6)

    [ended] = village.ended
    assert [line.speaker for line in ended.conversation.lines] == [PLAYER_ID, "ana"]
    assert ended.conversation.lines[-1].text in [text.format(name="Ben") for text in TURNED_AWAY]
    assert village.records[0].error == "cancelled"
    assert village.said("ben") == ["Hello!"]


async def test_an_npc_who_has_said_goodbye_doesnt_say_another() -> None:
    village = Village(["Hm. Right. [values: tradition]"], npcs=(BEN, ANA))
    village.players.say("Hello!", "ben")
    await village.run(5)
    village.players.say("Lovely weather.", "ben")
    await village.run(5)

    village.walk_to("ana", 1)
    village.players.say("Hi Ana.", "ana")

    [ended] = village.ended
    assert village.said("ben") == ["Hm.", "Right."] * 2
    assert ended.conversation.lines[-1].speaker == "ben"
    assert village.players.talk() is not None


SCENE = "".join(
    f"{name}: Line {n} about the allotments. [values: connection]\n"
    for n, name in enumerate(["Ben", "Cal"] * 4, 1)
)


def scene_or_reply(request: Request) -> str:
    if request.system.startswith("You write the dialogue"):
        return SCENE
    return "Oh, hello! Settling in? [values: connection]"


async def test_talking_to_a_resident_in_another_conversation_pulls_them_out_of_it() -> None:
    village = Village(npcs=(ANA, BEN, CAL), provider=FakeProvider(default=scene_or_reply))
    village.engine.start("ben", "cal")
    while len(village.spoken) < 2:
        await village.run(0.1)

    village.walk_to("ben", 1)
    assert village.players.say("Hi Ben.", "ben") is not None
    await village.run(10)

    scene, *_ = village.of(ConversationStarted)
    [ended] = village.ended
    assert ended.conversation.id == scene.conversation.id
    lines = ended.conversation.lines
    assert [line.text for line in lines[:2]] == [
        "Line 1 about the allotments.",
        "Line 2 about the allotments.",
    ]
    goodbye = lines[-1]
    assert len(lines) == 3
    assert goodbye.speaker == "ben"
    assert goodbye.text in [text.format(name="Cal") for text in GOODBYES[PLAYER]]
    assert goodbye.timestamp == lines[1].timestamp + timedelta(seconds=lines[1].duration + 0.5)
    talk = village.players.talk()
    assert talk is not None and talk.npc == "ben"
    said, reply, *_ = talk.conversation.lines
    assert said.text == "Hi Ben."
    assert reply.timestamp == goodbye.timestamp + timedelta(seconds=goodbye.duration)
    assert village.engine.state("ben")["talking_to"] == PLAYER_ID
    assert village.behaviour.minds["cal"].paused is False
    assert village.behaviour.minds["ben"].paused is True


async def test_the_npc_hears_the_player_until_the_conversation_ends() -> None:
    village = Village()
    village.players.say("Hi Ana.", "ana")
    await village.run(4)

    config = DEFAULT_PLAYER_CONFIG
    village.walk_to("ana", (config.say_range + config.leave_range) / 2)
    await village.run(0.2)
    assert village.players.say("Can you hear me from here?", "ana") is not None
    await village.run(4)

    assert village.ended == []
    assert len(village.script.requests) == 2
    village.walk_to("ana", config.leave_range + 0.5)
    assert village.players.say("And from here?", "ana") is None


async def test_the_reply_waits_until_the_goodbye_has_been_said_and_heard() -> None:
    village = Village(npcs=(ANA, BEN, CAL), provider=FakeProvider(default=scene_or_reply))
    village.engine.audio = audio = Audio(village.clock)
    village.world.bus.subscribe(LineSpoken, audio.make(4.0))
    village.engine.start("ben", "cal")
    while not village.spoken:
        await village.run(0.1)

    village.walk_to("ben", 1)
    village.players.say("Hi Ben.", "ben")
    await village.run(15)

    [ended] = village.ended
    goodbye = ended.conversation.lines[-1]
    assert goodbye.speaker == "ben"
    assert goodbye.text in [text.format(name="Cal") for text in GOODBYES[PLAYER]]
    talk = village.players.talk()
    assert talk is not None
    reply = next(line for line in talk.conversation.lines if line.speaker == "ben")
    heard = goodbye.timestamp + timedelta(seconds=4.0)
    assert heard <= reply.timestamp < heard + timedelta(seconds=0.2)
    assert ended.conversation.ended is not None and ended.conversation.ended <= reply.timestamp
    assert village.spoken.index(goodbye) < village.spoken.index(reply)


async def test_nobody_answers_from_too_far_or_while_asleep() -> None:
    village = Village()
    village.walk_to("ana", DEFAULT_PLAYER_CONFIG.say_range + 0.5)

    assert village.players.say("Hello?", "ana") is None
    assert village.players.say("Hello?", "nobody") is None

    village.walk_to("ana", 1)
    village.behaviour.minds["ana"].goal, village.behaviour.minds["ana"].walk = (
        Goal(Activity.SLEEP),
        None,
    )
    assert village.players.say("Hello?", "ana") is None
    assert [type(event) for event in village.events if isinstance(event, LineSpoken)] == []


async def test_an_npc_who_came_looking_says_hello() -> None:
    village = Village(["Hey, you're the new one! [values: connection]"])

    assert village.engine.request("ana", PLAYER_ID)
    await village.run(2)

    [started] = village.of(ConversationStarted)
    assert started.conversation.participants == ["ana", PLAYER_ID]
    assert "You've just walked up to Visitor." in village.script.prompts[0]
    assert village.said("ana") == ["Hey, you're the new one!"]


async def test_an_npc_whose_hello_gets_no_answer_leaves_quietly() -> None:
    village = Village()

    village.engine.request("ana", PLAYER_ID)
    await village.run(DEFAULT_PLAYER_CONFIG.silence + 5)

    assert len(village.script.requests) == 1
    [ended] = village.ended
    assert [line.speaker for line in ended.conversation.lines] == ["ana", "ana"]


async def test_nobody_comes_over_while_the_player_is_busy_or_away() -> None:
    village = Village()
    village.connected = False
    assert not village.engine.request("ana", PLAYER_ID)

    village.connected = True
    village.players.say("Hi Ana.", "ana")
    assert not village.engine.request("ben", PLAYER_ID)


async def test_a_sociable_npc_nearby_greets_the_player_and_an_unsociable_one_doesnt() -> None:
    village = Village(["Hello! New in town? [values: connection]"], npcs=(BEN, ANA))
    village.movement.place("ana", "square")

    await village.run(DEFAULT_PLAYER_CONFIG.look_every + 1)
    assert village.of(ConversationStarted) == []

    village.walk_to("ana", 2)
    await village.run(DEFAULT_PLAYER_CONFIG.look_every + 1)

    [started] = village.of(ConversationStarted)
    assert started.conversation.participants == ["ana", PLAYER_ID]
    assert village.said("ana")[0] == "Hello!"


async def test_the_player_and_residents_talk_only_on_the_same_map() -> None:
    village = Village(["Hello! New in town? [values: connection]"], npcs=(ANA,))
    here = village.movement.position("ana")
    assert here.map == "coffee_shop"
    village.movement.track(PLAYER_ID, Point(here.x + 1, here.y, VILLAGE_MAP))

    assert village.players.say("Hello?", "ana") is None
    await village.run(DEFAULT_PLAYER_CONFIG.look_every * 3)
    assert village.of(ConversationStarted) == []

    village.walk_to("ana", 1)
    await village.run(DEFAULT_PLAYER_CONFIG.look_every + 1)
    [started] = village.of(ConversationStarted)
    assert started.conversation.participants == ["ana", PLAYER_ID]


async def test_an_npc_who_dislikes_the_player_doesnt_greet_them() -> None:
    village = Village(relationships=[feeling(ANA, PLAYER_ID, like=0.05, trust=0.1)])

    await village.run(DEFAULT_PLAYER_CONFIG.look_every * 3)

    assert village.of(ConversationStarted) == []


async def test_an_npc_with_an_urgent_need_doesnt_greet_the_player() -> None:
    village = Village(
        ["Hello! New in town? [values: connection]"],
        npcs=(ANA,),
        player=PlayerConfig(greet_cooldown=0),
    )
    village.behaviour.minds["ana"].needs[Need.BLADDER] = 0.95

    await village.run(DEFAULT_PLAYER_CONFIG.look_every * 3)
    assert village.of(ConversationStarted) == []

    village.behaviour.minds["ana"].needs[Need.BLADDER] = 0.2
    await village.run(DEFAULT_PLAYER_CONFIG.look_every + 1)
    [started] = village.of(ConversationStarted)
    assert started.conversation.participants == ["ana", PLAYER_ID]


async def test_an_npc_who_leaves_the_player_alone_doesnt_greet_them_until_let_go() -> None:
    village = Village(["Hello! New in town? [values: connection]"], npcs=(ANA,))
    village.behaviour.leave_player_alone.add("ana")

    await village.run(DEFAULT_PLAYER_CONFIG.look_every * 3)
    assert village.of(ConversationStarted) == []

    village.behaviour.leave_player_alone.discard("ana")
    await village.run(DEFAULT_PLAYER_CONFIG.look_every + 1)
    [started] = village.of(ConversationStarted)
    assert started.conversation.participants == ["ana", PLAYER_ID]


async def test_a_claude_code_process_is_started_before_the_npc_needs_it() -> None:
    village = Village(npcs=(BEN,))
    system = system_prompt(BEN)

    await village.run(DEFAULT_PLAYER_CONFIG.look_every + 0.5)
    assert village.provider.warmed == [(system, "claude-haiku-4-5")]

    village.players.say("Hello.", "ben")
    await village.run(3)
    assert village.provider.warmed == [(system, "claude-haiku-4-5")] * 2
    assert {request.model for request in village.provider.requests} == {"claude-haiku-4-5"}


@pytest.mark.parametrize(
    ("chunks", "sentences"),
    [
        (["Hello there. How", " are you?\n[values: connection]"], ["Hello there.", "How are you?"]),
        (["Mr. Lee says hi! ", "Dr. Who? ", "No."], ["Mr. Lee says hi!", "Dr. Who?", "No."]),
        (['"Well. ', 'I never."'], ["Well.", "I never."]),
        (["*leans in. whispers* ", "Did you hear?"], ["Did you hear?"]),
        (["Ana: Hi.\nVisitor: Hello.\nAna: Bye."], ["Hi."]),
        (["[values: honesty]\nHonestly? ", "Yes."], ["Honestly?", "Yes."]),
        (["Hi. [laughs] Okay."], ["Hi.", "[laughs] Okay."]),
        (["Wait…", " what?"], ["Wait…", "what?"]),
    ],
)
def test_a_reply_comes_out_in_sentences(chunks: list[str], sentences: list[str]) -> None:
    splitter = Sentences(["Ana", "Ana Test"], ["Visitor"])

    out = [sentence for chunk in chunks for sentence in splitter.feed(chunk)]

    assert out + splitter.end() == sentences


def test_a_sentence_is_out_as_soon_as_the_next_begins_or_the_tag_starts() -> None:
    splitter = Sentences()

    assert splitter.feed("Hi there.") == []
    assert splitter.feed(" So") == ["Hi there."]
    assert splitter.feed(" anyway!") == []
    assert splitter.feed("\n[val") == ["So anyway!"]
    assert splitter.feed("ues: connection]") == []
    assert splitter.end() == []
    assert splitter.draft.values == (CoreValue.CONNECTION,)


def streamed(text: str) -> list[str]:
    splitter = Sentences()
    words = re.findall(r"\S+\s*", f"{text}\n[values: connection]")
    return [sentence for word in words for sentence in splitter.feed(word)] + splitter.end()


@pytest.mark.parametrize(
    ("text", "sentences"),
    [
        (
            "Oh mate, depends who you ask—some people do the whole farmers market thing.",
            ["Oh mate, depends who you ask—", "some people do the whole farmers market thing."],
        ),
        (
            "I painted the east wall last spring; it took me most of the summer.",
            ["I painted the east wall last spring;", "it took me most of the summer."],
        ),
        (
            "The market is the place to be - everyone turns up on a Saturday morning.",
            ["The market is the place to be -", "everyone turns up on a Saturday morning."],
        ),
        (
            "The coffee is decent but the pastries are something else, so get there before nine.",
            [
                "The coffee is decent but the pastries are something else,",
                "so get there before nine.",
            ],
        ),
        (
            "Hi there. Go and find Marcus at the maker space—he knows everyone around here.",
            ["Hi there.", "Go and find Marcus at the maker space—he knows everyone around here."],
        ),
    ],
)
def test_a_long_first_sentence_is_cut_at_a_clause(text: str, sentences: list[str]) -> None:
    assert streamed(text) == sentences


@pytest.mark.parametrize(
    "text",
    [
        "Oh man, honestly I just grab whatever's cheapest and they always throw in a pastry.",
        "The space, man—nobody's watching what you do or telling you it's wrong.",
        "Go and find Marcus at the maker space—you know?",
        "The coffee is decent but the pastries are something else, really.",
        "When I'm not working at the bakery I like painting, hiking, swimming and old novels.",
        "It's a well-known spot for the after-work crowd and their dogs on a sunny evening.",
        "We usually open the whole shop from 9–5 most days, except Sundays of course.",
        "The bakery is at its busiest between 7 -- 11 on weekdays and quiet after lunch.",
    ],
)
def test_a_first_sentence_without_a_good_clause_stays_whole(text: str) -> None:
    assert streamed(text) == [text]


def test_a_dash_in_a_stage_direction_isnt_a_clause() -> None:
    text = "*gestures broadly at the big painted wall behind her—grinning* Come and see it."

    assert streamed(text) == ["Come and see it."]


def test_a_clause_is_cut_once_enough_words_follow_it() -> None:
    splitter = Sentences()

    assert splitter.feed("Go and find Marcus at the maker space—he knows") == []
    assert splitter.feed(" everyone around") == []
    assert splitter.feed(" ") == ["Go and find Marcus at the maker space—"]
    assert splitter.feed("here. Bye") == ["he knows everyone around here."]


def test_split() -> None:
    assert split("One. Two? Three!") == ["One.", "Two?", "Three!"]
    assert split("") == [""]


@pytest.mark.parametrize(
    "text",
    [
        "Bye!",
        "ok goodbye",
        "Good-bye, Ana.",
        "See you later!",
        "see ya",
        "Thanks, take care :)",
        "Gotta go now.",
        "I have to run",
        "Catch you later",
        "talk to you soon",
        "Good night!",
        "Cheerio",
        "Nice to see you, bye",
        "Nice to see you. See you later!",
        "see you soon",
        "Hope to see you soon.",
        "Thanks, see you around",
        "ok see you",
        "It was nice to see you.",
        "It was lovely to see you!",
        "Was great to see you.",
        "It's been good to see you.",
    ],
)
def test_goodbyes(text: str) -> None:
    assert says_goodbye(text)


@pytest.mark.parametrize(
    "text",
    [
        "Hi!",
        "By the way, where's the bakery?",
        "I see you have a dog.",
        "I need to go to the shop later, what's open?",
        "I take care of my mum.",
        "I'll tell you later.",
        "Oh hi, nice to see you.",
        "Good to see ya!",
        "Lovely to see you again.",
        "Oh hi, I was hoping to see you.",
        "nice to see you.",
    ],
)
def test_not_goodbyes(text: str) -> None:
    assert not says_goodbye(text)


RED_PLANET = work("cal-1", "cal", "Red Planet", START - timedelta(hours=3), tags=["mars"])
SAW_IT = 'I saw Cal Test\'s mural "Red Planet" on the tower. Brave stuff.'


async def test_a_work_is_listed_until_the_resident_has_answered_it_coming_up() -> None:
    village = Village(npcs=(ANA, BEN, CAL))
    village.engine.work = {RED_PLANET.id: RED_PLANET}.get
    village.store.add(remembers("ana", RED_PLANET, SAW_IT, START - timedelta(hours=1)))

    for said in ("Hi!", "What do you make of Cal's mural?", "Anything else new?"):
        village.players.say(said, "ana")
        await village.run(1)

    *answering, after = village.script.prompts
    for prompt in answering:
        assert f"Works by others you might bring up:\n- {SAW_IT}\n\n" in prompt
    assert "Red Planet" not in after


async def test_a_resident_stands_by_their_own_work_and_never_sees_the_players() -> None:
    theirs = work("ana-1", "ana", "Fair Shares", START - timedelta(hours=2))
    painted = 'I painted "Fair Shares" on the tower. Everyone eats.'
    village = Village(npcs=(ANA, BEN, CAL))
    village.engine.work = {w.id: w for w in (theirs, RED_PLANET)}.get
    village.store.add(
        remembers("ana", theirs, painted, START - timedelta(hours=2)),
        remembers(PLAYER_ID, RED_PLANET, SAW_IT, START),
    )

    village.players.say("Hi!", "ana")
    await village.run(1)

    [prompt] = village.script.prompts
    assert f"Your own works, which you might bring up and stand by:\n- {painted}" in prompt
    assert "Red Planet" not in prompt


def said(speaker: str, text: str) -> Line:
    return Line(id=1, conversation_id="c", speaker=speaker, text=text, timestamp=START, duration=1)


def writing(id: str, artist: str, title: str, *tags: str) -> Work:
    return work(id, artist, title, START, medium=Medium.WRITING, tags=tags)


SUPPER = writing("tobias-2", "tobias", "Look Before You Tell the Supper Table", "river", "village")
TABLES = writing("tobias-1", "tobias", "The Tables by the Water", "river", "repair")
NOTICE = writing("henrietta-1", "henrietta", "Notice: Devices in Your Dwelling", "passwords")
TARGETS = writing("raymond-1", "raymond", "Q4 Targets: Plan the Mountain, Then Climb It", "mars")
DOOR = work("ingrid-1", "ingrid", "Open The Door", START, tags=["freedom", "raven"])
FIRST_COAT = work("kofi-1", "kofi", "First Coat", START, tags=["mars"]).model_copy(
    update={"wall": "daily_grind"}
)


@pytest.mark.parametrize(
    ("work", "owner", "speaker", "text", "expected"),
    [
        (RED_PLANET, "ana", "ana", "Have you seen that Red Planet thing?", True),
        (RED_PLANET, "ana", PLAYER_ID, "What do you make of Cal's mural?", True),
        (RED_PLANET, "ana", "ana", "That Mars business of Cal's? Brave.", True),
        (RED_PLANET, "ana", PLAYER_ID, "Seen the new mural on the tower?", True),
        (RED_PLANET, "cal", "cal", "Have you seen my mural yet?", True),
        (RED_PLANET, "cal", PLAYER_ID, "I love your painting!", True),
        (DOOR, "ana", "ana", 'Have you seen "Open The Door" yet?', True),
        (DOOR, "ana", PLAYER_ID, "Ingrid's open the door thing is lovely.", True),
        (NOTICE, "henrietta", "henrietta", "Have you read my notice about devices?", True),
        (TABLES, "tobias", PLAYER_ID, "I read your poem about the river.", True),
        (TABLES, "tobias", PLAYER_ID, "Tobias, I loved your poem.", True),
        (NOTICE, "ana", PLAYER_ID, "Have you read the notice about devices?", True),
        (FIRST_COAT, "priya", PLAYER_ID, "Seen the new mural by the Daily Grind?", True),
        (RED_PLANET, "ana", PLAYER_ID, "I love your painting!", False),
        (RED_PLANET, "ana", "ana", "My painting days are over.", False),
        (RED_PLANET, "ana", PLAYER_ID, "Cal's been busy.", False),
        (RED_PLANET, "ana", PLAYER_ID, "There are murals everywhere here.", False),
        (RED_PLANET, "ana", "ana", "First time at the tower, yes?", False),
        (SUPPER, "ana", PLAYER_ID, "Tell me about the village.", False),
        (SUPPER, "ana", PLAYER_ID, "Where can I get a decent table for supper?", False),
        (TABLES, "ana", PLAYER_ID, "Is the river water clean?", False),
        (NOTICE, "ana", PLAYER_ID, "Did you notice anything odd today?", False),
        (DOOR, "ana", PLAYER_ID, "Could you open the door for me?", False),
        (TABLES, "tobias", PLAYER_ID, "Hi! What's your story?", False),
        (TARGETS, "raymond", PLAYER_ID, "What's your plan for today?", False),
        (TABLES, "tobias", PLAYER_ID, "Tobias, how's the river today?", False),
        (SUPPER, "tobias", PLAYER_ID, "Morning Tobias! Tell me about the village.", False),
        (TARGETS, "raymond", PLAYER_ID, "Hi Raymond! Any plans for the weekend?", False),
        (FIRST_COAT, "priya", PLAYER_ID, "Did you notice the new menu at the Daily Grind?", False),
        (RED_PLANET, "ana", PLAYER_ID, "Did you notice the tower on the way in?", False),
        (TABLES, "ana", PLAYER_ID, "Did you notice how high the river is?", False),
    ],
)
def test_when_a_work_has_come_up(
    work: Work, owner: str, speaker: str, text: str, expected: bool
) -> None:
    topic = WorkTopic(remembers(owner, work, "I know it.", START), work)

    assert came_up(topic, work.artist.title(), [said(speaker, text)]) is expected


class Writer:
    """Writes `reply` for each cue, recording what it was given."""

    def __init__(self, reply: str | None) -> None:
        self.reply = reply
        self.calls: list[tuple[Cue, list[str]]] = []

    async def __call__(self, cue: Cue, lines: Sequence[Line]) -> str | None:
        self.calls.append((cue, [line.text for line in lines]))
        return self.reply


async def test_a_writer_writes_the_npcs_reply_instead_of_the_llm() -> None:
    village = Village()
    village.players.writers["ana"] = writer = Writer("One flat white, coming up. Oat milk?")

    village.players.say("A flat white, please.", "ana")
    await village.run()

    assert writer.calls == [(Cue.REPLY, ["A flat white, please."])]
    assert village.said("ana") == ["One flat white, coming up.", "Oat milk?"]
    assert village.script.requests == []


async def test_a_writer_that_returns_none_leaves_the_reply_to_the_llm() -> None:
    village = Village()
    village.players.writers["ana"] = writer = Writer(None)

    village.players.say("Hi, I'm new here.", "ana")
    await village.run()

    assert len(writer.calls) == 1
    assert village.said("ana") == ["Lovely to meet you.", "Settling in?"]
    assert len(village.script.requests) == 1


async def test_another_npcs_writer_leaves_the_reply_to_the_llm() -> None:
    village = Village()
    village.players.writers["ben"] = writer = Writer("Not me.")

    village.players.say("Hi, I'm new here.", "ana")
    await village.run()

    assert writer.calls == []
    assert village.said("ana") == ["Lovely to meet you.", "Settling in?"]


async def test_an_interjection_opens_a_conversation_the_player_can_answer() -> None:
    village = Village()

    assert village.players.interject("ana", "Flat white for you!")
    await village.run(1)

    [started] = village.of(ConversationStarted)
    assert started.conversation.participants == ["ana", PLAYER_ID]
    assert village.said("ana") == ["Flat white for you!"]
    assert village.script.requests == []
    village.players.say("Thanks!", "ana")
    await village.run()
    assert village.said("ana") == ["Flat white for you!", "Lovely to meet you.", "Settling in?"]
    assert len(village.of(ConversationStarted)) == 1


async def test_an_interjection_joins_the_conversation_going_on() -> None:
    village = Village()
    village.players.say("Hi, I'm new here.", "ana")
    await village.run()

    assert village.players.interject("ana", "Your tea's ready.")
    await village.run(3)

    assert village.said("ana")[-1] == "Your tea's ready."
    assert len(village.of(ConversationStarted)) == 1


async def test_nobody_interjects_while_the_player_talks_to_someone_else() -> None:
    village = Village()
    village.walk_to("ben", 1)
    village.players.say("Hello Ben.", "ben")
    await village.run()

    assert not village.players.interject("ana", "Flat white for you!")
    assert "Flat white for you!" not in village.said("ana")
