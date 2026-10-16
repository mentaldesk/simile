import asyncio
import itertools
import math
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from simile.conversation import LineDrafted
from simile.protocol import SAMPLE_RATE, AudioChunk
from simile.schema import PLAYER_ID, Conversation, Id, Line, Voice
from simile.sim import ConversationEnded, ConversationStarted, LineSpoken
from simile.voice import FakeSynthesiser, VoiceService
from simile.voicing import DEFAULT_CONFIG, VoicingConfig
from simile.voicing.voicing import Voicing

NOW = datetime(2026, 1, 1, 10, tzinfo=UTC)
VOICE = Voice(
    description="Warm.", reference_line="Hello.", reference_clip="content/voices/kofi.wav"
)
VOICED = ("mei", "viktor", "suki")


class Village:
    """Voicing with everyone at fixed tiles, recording what it sends and when."""

    def __init__(self, voice: VoiceService, config: VoicingConfig) -> None:
        self.at: dict[Id, tuple[float, float]] = {
            "mei": (0, 0),
            "viktor": (1, 0),
            "suki": (0, 2),
            "tom": (1, 1),
            PLAYER_ID: (3, 0),
        }
        self.sent: list[tuple[float, AudioChunk]] = []
        self.listening = True
        self.voicing = Voicing(
            voice, self.distance, self.record, listening=lambda: self.listening, config=config
        )
        self._ids = itertools.count(1)

    def distance(self, a: Id, b: Id) -> float:
        return math.dist(self.at[a], self.at[b])

    def record(self, chunk: AudioChunk) -> None:
        self.sent.append((asyncio.get_running_loop().time(), chunk))

    def start(self, *participants: Id) -> str:
        conversation = Conversation(
            id=f"talk-{next(self._ids)}", participants=list(participants), started=NOW
        )
        self.voicing.on_started(ConversationStarted(conversation))
        return conversation.id

    def line(self, conversation: str, speaker: Id, text: str) -> Line:
        return Line(
            id=next(self._ids),
            conversation_id=conversation,
            speaker=speaker,
            text=text,
            timestamp=NOW,
            duration=1,
        )

    def draft(self, conversation: str, speaker: Id, text: str) -> Line:
        line = self.line(conversation, speaker, text)
        self.voicing.on_drafted(LineDrafted(line))
        return line

    def speak(self, line: Line) -> bool:
        """What the protocol forwarder sends as `voiced`."""
        voiced = self.voicing.voiced(line)
        self.voicing.on_spoken(LineSpoken(line))
        return voiced

    def say(self, conversation: str, speaker: Id, text: str) -> tuple[Line, bool]:
        line = self.draft(conversation, speaker, text)
        return line, self.speak(line)

    def end(self, conversation: str, *participants: Id) -> None:
        ended = Conversation(id=conversation, participants=list(participants), started=NOW)
        self.voicing.on_ended(ConversationEnded(ended))

    def move_player(self, x: float, y: float) -> None:
        self.at[PLAYER_ID] = (x, y)
        self.voicing.tick(0.1)

    def chunks(self, line: Line) -> list[AudioChunk]:
        return [chunk for _, chunk in self.sent if chunk.line_id == line.id]

    def times(self, line: Line) -> list[float]:
        return [at for at, chunk in self.sent if chunk.line_id == line.id]

    async def heard(self, line: Line) -> list[AudioChunk]:
        await until(lambda: any(chunk.last for chunk in self.chunks(line)))
        return self.chunks(line)


@asynccontextmanager
async def village(
    synthesiser: FakeSynthesiser, config: VoicingConfig = DEFAULT_CONFIG
) -> AsyncIterator[Village]:
    async with VoiceService(synthesiser) as voice:
        for npc in VOICED:
            await voice.add_voice(npc, VOICE)
        world = Village(voice, config)
        try:
            yield world
        finally:
            await world.voicing.close()


async def until(condition: Callable[[], bool]) -> None:
    async with asyncio.timeout(2):
        while not condition():
            await asyncio.sleep(0.001)


async def settle() -> None:
    await asyncio.sleep(0.05)


def pcm(synthesiser: FakeSynthesiser) -> list[bytes]:
    return [synthesiser.chunk(i) for i in range(synthesiser.chunks)]


def test_voices_lines_within_earshot(synthesiser: FakeSynthesiser) -> None:
    async def scenario() -> tuple[Line, bool, list[AudioChunk]]:
        async with village(synthesiser) as world:
            talk = world.start("mei", "viktor")
            line, voiced = world.say(talk, "mei", "Morning, Viktor.")
            return line, voiced, await world.heard(line)

    line, voiced, chunks = asyncio.run(scenario())

    assert voiced
    assert [chunk.pcm for chunk in chunks[:-1]] == pcm(synthesiser)
    assert [chunk.sequence for chunk in chunks] == list(range(synthesiser.chunks + 1))
    assert chunks[-1] == AudioChunk(line.id, synthesiser.chunks, b"", last=True)


def test_leaves_conversations_beyond_earshot_unvoiced(synthesiser: FakeSynthesiser) -> None:
    async def scenario() -> tuple[bool, list[AudioChunk]]:
        async with village(synthesiser) as world:
            world.move_player(10, 0)
            talk = world.start("mei", "viktor")
            line, voiced = world.say(talk, "mei", "Morning, Viktor.")
            await settle()
            return voiced, world.chunks(line)

    assert asyncio.run(scenario()) == (False, [])
    assert synthesiser.started == []


def test_writes_a_line_ahead_and_sends_it_once_spoken(synthesiser: FakeSynthesiser) -> None:
    async def scenario() -> tuple[list[AudioChunk], list[AudioChunk]]:
        async with village(synthesiser) as world:
            talk = world.start("mei", "viktor")
            line = world.draft(talk, "viktor", "Morning, Mei.")
            await until(lambda: "Morning, Mei." in synthesiser.closed)
            await settle()
            before = world.chunks(line)
            world.speak(line)
            return before, await world.heard(line)

    before, after = asyncio.run(scenario())

    assert before == []
    assert len(after) == synthesiser.chunks + 1


def test_holds_a_line_until_the_one_before_has_played(synthesiser: FakeSynthesiser) -> None:
    async def scenario() -> tuple[list[float], list[float]]:
        async with village(synthesiser) as world:
            talk = world.start("mei", "viktor")
            first, _ = world.say(talk, "mei", "Morning, Viktor.")
            second, _ = world.say(talk, "viktor", "Morning, Mei.")
            await world.heard(second)
            return world.times(first), world.times(second)

    first, second = asyncio.run(scenario())

    played = synthesiser.chunks * len(synthesiser.chunk(0)) / 2 / SAMPLE_RATE
    assert second[0] >= first[0] + DEFAULT_CONFIG.jitter_buffer + played - 0.001
    assert second[0] >= first[-1]


def test_starts_with_the_next_line_when_the_player_comes_near(
    synthesiser: FakeSynthesiser,
) -> None:
    async def scenario() -> tuple[bool, bool, list[AudioChunk]]:
        async with village(synthesiser) as world:
            world.move_player(20, 0)
            talk = world.start("mei", "viktor")
            _, far = world.say(talk, "mei", "Morning, Viktor.")
            line = world.draft(talk, "viktor", "Morning, Mei.")
            world.move_player(5, 5)
            near = world.speak(line)
            return far, near, await world.heard(line)

    far, near, chunks = asyncio.run(scenario())

    assert (far, near) == (False, True)
    assert synthesiser.started == ["Morning, Mei."]
    assert len(chunks) == synthesiser.chunks + 1


def test_stops_when_the_player_walks_away(synthesiser: FakeSynthesiser) -> None:
    sentence = "Have you seen the state of the square?"
    gate = synthesiser.gate(sentence)

    async def scenario() -> tuple[list[AudioChunk], int, bool]:
        async with village(synthesiser) as world:
            talk = world.start("mei", "viktor")
            line, _ = world.say(talk, "mei", sentence)
            gate.release(1)
            await until(lambda: len(world.chunks(line)) == 1)
            ahead = world.draft(talk, "viktor", "I have.")
            world.move_player(10, 0)
            await settle()
            sent_at_ten = len(world.chunks(line))
            world.move_player(13, 0)
            chunks = await world.heard(line)
            gate.release(synthesiser.chunks)
            await until(lambda: sentence in synthesiser.closed)
            return chunks, sent_at_ten, world.speak(ahead)

    chunks, sent_at_ten, ahead_voiced = asyncio.run(scenario())

    assert sent_at_ten == 1
    assert chunks[1:] == [AudioChunk(chunks[0].line_id, 1, b"", last=True)]
    assert synthesiser.made[sentence] < synthesiser.chunks
    assert not ahead_voiced


def test_never_voices_the_player_or_npcs_without_a_voice(synthesiser: FakeSynthesiser) -> None:
    async def scenario() -> list[bool]:
        async with village(synthesiser) as world:
            talk = world.start(PLAYER_ID, "tom")
            player = world.speak(world.line(talk, PLAYER_ID, "Hello!"))
            _, tom = world.say(talk, "tom", "Hello yourself.")
            return [player, tom]

    assert asyncio.run(scenario()) == [False, False]


def test_stops_when_the_player_interrupts(synthesiser: FakeSynthesiser) -> None:
    sentence = "Well, it all started on Tuesday."
    gate = synthesiser.gate(sentence)

    async def scenario() -> tuple[list[AudioChunk], list[AudioChunk], bool]:
        async with village(synthesiser) as world:
            talk = world.start(PLAYER_ID, "mei")
            line, _ = world.say(talk, "mei", sentence)
            gate.release(1)
            await until(lambda: len(world.chunks(line)) == 1)
            queued = world.draft(talk, "mei", "Or was it Wednesday?")
            world.speak(world.line(talk, PLAYER_ID, "Sorry, I have to go."))
            cut = await world.heard(line)
            await settle()
            return cut, world.chunks(queued), world.voicing.voiced(queued)

    cut, queued, queued_voiced = asyncio.run(scenario())

    assert cut[1:] == [AudioChunk(cut[0].line_id, 1, b"", last=True)]
    assert queued == []
    assert not queued_voiced


def test_player_replies_go_ahead_of_overheard_lines(synthesiser: FakeSynthesiser) -> None:
    overheard = "Did you hear about the bakery?"
    gate = synthesiser.gate(overheard)

    async def scenario() -> tuple[list[AudioChunk], list[AudioChunk]]:
        async with village(synthesiser) as world:
            nearby = world.start("viktor", "suki")
            ahead = world.draft(nearby, "viktor", overheard)
            gate.release(1)
            await until(lambda: synthesiser.made[overheard] == 1)
            talk = world.start(PLAYER_ID, "mei")
            reply, _ = world.say(talk, "mei", "Nice to meet you.")
            await settle()
            gate.release(1)
            heard = await world.heard(reply)
            gate.release(synthesiser.chunks)
            world.speak(ahead)
            return heard, await world.heard(ahead)

    reply, overheard_chunks = asyncio.run(scenario())

    assert len(reply) == synthesiser.chunks + 1
    assert synthesiser.started == [overheard, "Nice to meet you.", overheard]
    assert [chunk.pcm for chunk in overheard_chunks[:-1]] == pcm(synthesiser)


def test_a_line_that_fails_to_voice_is_unvoiced(synthesiser: FakeSynthesiser) -> None:
    synthesiser.failing.add("Hmm.")

    async def scenario() -> tuple[bool, list[AudioChunk]]:
        async with village(synthesiser) as world:
            talk = world.start("mei", "viktor")
            line = world.draft(talk, "mei", "Hmm.")
            await until(lambda: "Hmm." in synthesiser.closed)
            await settle()
            voiced = world.speak(line)
            await settle()
            return voiced, world.chunks(line)

    assert asyncio.run(scenario()) == (False, [])


def test_an_ending_finishes_spoken_lines_and_drops_the_rest(
    synthesiser: FakeSynthesiser,
) -> None:
    async def scenario() -> tuple[list[AudioChunk], list[AudioChunk]]:
        async with village(synthesiser) as world:
            talk = world.start("mei", "viktor")
            last, _ = world.say(talk, "mei", "Bye then.")
            unsaid = world.draft(talk, "viktor", "Bye.")
            world.end(talk, "mei", "viktor")
            heard = await world.heard(last)
            await settle()
            return heard, world.chunks(unsaid)

    heard, unsaid = asyncio.run(scenario())

    assert len(heard) == synthesiser.chunks + 1
    assert unsaid == []


def test_voices_nothing_without_a_client(synthesiser: FakeSynthesiser) -> None:
    async def scenario() -> bool:
        async with village(synthesiser) as world:
            world.listening = False
            talk = world.start("mei", "viktor")
            _, voiced = world.say(talk, "mei", "Morning, Viktor.")
            return voiced

    assert not asyncio.run(scenario())


def test_sends_audio_no_more_than_the_lead_ahead_of_playback() -> None:
    synthesiser = FakeSynthesiser(chunks=30)
    config = VoicingConfig(lead=0.03)

    async def scenario() -> list[tuple[float, AudioChunk]]:
        async with village(synthesiser, config) as world:
            talk = world.start("mei", "viktor")
            line, _ = world.say(talk, "mei", "Let me tell you about the harvest.")
            await world.heard(line)
            return [(at, chunk) for at, chunk in world.sent if chunk.pcm]

    ahead = queued_on_the_client(asyncio.run(scenario()))

    assert len(ahead) == synthesiser.chunks - 1
    assert max(ahead) <= config.lead + 0.002


def queued_on_the_client(sent: list[tuple[float, AudioChunk]]) -> list[float]:
    """How much audio C3's timeline still had to play as each chunk after the first arrived."""
    start, samples, ahead = -math.inf, 0, []
    for at, chunk in sent:
        end = start + samples / SAMPLE_RATE
        if samples:
            ahead.append(end - at)
        if not samples or end < at + 0.01:
            start, samples = at + DEFAULT_CONFIG.jitter_buffer, 0
        samples += len(chunk.pcm) // 2
    return ahead


def test_a_player_reply_cuts_an_overheard_line_being_heard(
    synthesiser: FakeSynthesiser,
) -> None:
    overheard = "Did you hear about the bakery?"
    gate = synthesiser.gate(overheard)

    async def scenario() -> tuple[list[AudioChunk], bool, list[AudioChunk]]:
        async with village(synthesiser) as world:
            nearby = world.start("viktor", "suki")
            line, _ = world.say(nearby, "viktor", overheard)
            gate.release(1)
            await until(lambda: len(world.chunks(line)) == 1)
            talk = world.start(PLAYER_ID, "mei")
            reply, voiced = world.say(talk, "mei", "Nice to meet you.")
            cut = await world.heard(line)
            gate.release(1)
            return cut, voiced, await world.heard(reply)

    cut, voiced, reply = asyncio.run(scenario())

    assert cut[1:] == [AudioChunk(cut[0].line_id, 1, b"", last=True)]
    assert synthesiser.made[overheard] < synthesiser.chunks
    assert voiced
    assert [chunk.pcm for chunk in reply[:-1]] == pcm(synthesiser)


def test_an_ending_never_restarts_lines_left_unspoken(synthesiser: FakeSynthesiser) -> None:
    sentence = "Right, I'm off."
    gate = synthesiser.gate(sentence)

    async def scenario() -> list[AudioChunk]:
        async with village(synthesiser) as world:
            talk = world.start("mei", "viktor")
            last, _ = world.say(talk, "mei", sentence)
            gate.release(1)
            await until(lambda: len(world.chunks(last)) == 1)
            unsaid = world.draft(talk, "viktor", "Bye.")
            world.end(talk, "mei", "viktor")
            await settle()
            world.voicing.tick(0.1)
            gate.release(synthesiser.chunks)
            await world.heard(last)
            await settle()
            return world.chunks(unsaid)

    assert asyncio.run(scenario()) == []
    assert synthesiser.started == [sentence]


def test_voices_no_more_than_max_voiced_until_one_ends(synthesiser: FakeSynthesiser) -> None:
    async def scenario() -> tuple[bool, bool, bool]:
        async with village(synthesiser, VoicingConfig(max_voiced=1)) as world:
            first = world.start("mei", "viktor")
            _, voiced = world.say(first, "mei", "Morning, Viktor.")
            second = world.start("suki", "tom")
            _, crowded = world.say(second, "suki", "Morning, Tom.")
            world.end(first, "mei", "viktor")
            _, freed = world.say(second, "suki", "Lovely day for it.")
            return voiced, crowded, freed

    assert asyncio.run(scenario()) == (True, False, True)


def test_the_players_conversation_silences_the_farthest_overheard_one(
    synthesiser: FakeSynthesiser,
) -> None:
    async def scenario() -> tuple[bool, bool, bool]:
        async with village(synthesiser, VoicingConfig(max_voiced=2)) as world:
            world.at.update({"ana": (9, 0), "ben": (9, 1)})
            for npc in ("ana", "ben"):
                await world.voicing.voice.add_voice(npc, VOICE)
            near = world.start("mei", "viktor")
            far = world.start("ana", "ben")
            talk = world.start(PLAYER_ID, "suki")
            _, reply = world.say(talk, "suki", "Nice to meet you.")
            _, near_voiced = world.say(near, "mei", "Morning, Viktor.")
            _, far_voiced = world.say(far, "ana", "Morning, Ben.")
            return reply, near_voiced, far_voiced

    assert asyncio.run(scenario()) == (True, True, False)
