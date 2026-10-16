import asyncio
import itertools
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
    system_prompt,
)
from simile.conversation.player import (
    DEFAULT_PLAYER_CONFIG,
    PlayerConfig,
    PlayerConversations,
    Sentences,
    says_goodbye,
    split,
)
from simile.llm import CallRecord, FakeProvider, LLMClient, LLMError, Request
from simile.memory import MemoryStore
from simile.npc import load_npcs
from simile.reflection import Deed, Extraction, Reflection, Reflector
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
from simile.social import describe, meet
from simile.world import Movement, Point
from simile.world.map import load_map

pytestmark = pytest.mark.anyio

TOWN = load_map()
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
        self.movement = Movement(TOWN, self.world.bus)
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
        self.movement.track(PLAYER_ID, Point(here.x + tiles, here.y))

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
    assert prompt.endswith("Say your next line to Visitor.")
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


async def test_talking_to_someone_else_ends_the_first_conversation() -> None:
    village = Village()
    village.players.say("Hi Ana.", "ana")
    await village.run(4)

    village.walk_to("ben", 1)
    village.players.say("Hi Ben.", "ben")
    await village.run(1)

    first, second = village.of(ConversationStarted)
    assert [event.conversation.id for event in village.ended] == [first.conversation.id]
    assert second.conversation.participants == [PLAYER_ID, "ben"]


async def test_talking_to_someone_busy_keeps_the_conversation_going_on() -> None:
    village = Village(npcs=(ANA, BEN, CAL))
    village.players.say("Hi Ana.", "ana")
    await village.run(4)
    village.engine.start("ben", "cal")

    village.walk_to("ben", 1)
    assert village.players.say("Hi Ben.", "ben") is None

    assert village.ended == []
    talk = village.players.talk()
    assert talk is not None and talk.npc == "ana"


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


async def test_nobody_answers_from_too_far_or_while_busy() -> None:
    village = Village()
    village.walk_to("ana", DEFAULT_PLAYER_CONFIG.say_range + 0.5)

    assert village.players.say("Hello?", "ana") is None
    assert village.players.say("Hello?", "nobody") is None

    village.walk_to("ana", 1)
    village.engine.start("ana", "ben")
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


async def test_an_npc_who_dislikes_the_player_doesnt_greet_them() -> None:
    village = Village(relationships=[feeling(ANA, PLAYER_ID, like=0.05, trust=0.1)])

    await village.run(DEFAULT_PLAYER_CONFIG.look_every * 3)

    assert village.of(ConversationStarted) == []


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
    ],
)
def test_not_goodbyes(text: str) -> None:
    assert not says_goodbye(text)
