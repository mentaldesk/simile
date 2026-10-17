import asyncio
import threading
import time
from collections.abc import AsyncIterator, Callable, Generator
from contextlib import asynccontextmanager

import pytest

from simile.schema import Voice
from simile.voice import FakeSynthesiser, Priority, VoiceService

SMITH = Voice(
    description="Deep and gravelly.",
    reference_line="Aye, I've been working this forge for nigh on fifty years.",
    reference_clip="voice-lab/voices/dwarf_smith.wav",
)


@asynccontextmanager
async def smith_voice(synthesiser: FakeSynthesiser) -> AsyncIterator[VoiceService]:
    async with VoiceService(synthesiser) as voice:
        await voice.add_voice("smith", SMITH)
        yield voice


async def collect(speech: AsyncIterator[bytes]) -> list[bytes]:
    return [pcm async for pcm in speech]


async def until(condition: Callable[[], bool]) -> None:
    async with asyncio.timeout(2):
        while not condition():
            await asyncio.sleep(0.001)


def all_chunks(synthesiser: FakeSynthesiser) -> list[bytes]:
    return [synthesiser.chunk(i) for i in range(synthesiser.chunks)]


def test_speaks_a_sentence_in_chunks(synthesiser: FakeSynthesiser) -> None:
    async def scenario() -> list[bytes]:
        async with smith_voice(synthesiser) as voice:
            return await collect(voice.speak("smith", "Hello."))

    assert asyncio.run(scenario()) == all_chunks(synthesiser)


def test_uses_the_synthesiser_from_one_thread(synthesiser: FakeSynthesiser) -> None:
    async def scenario() -> None:
        async with smith_voice(synthesiser) as voice:
            await collect(voice.speak("smith", "One."))
            await collect(voice.speak("smith", "Two."))

    asyncio.run(scenario())

    assert synthesiser.loaded
    assert len(synthesiser.threads) == 1
    assert synthesiser.threads != {threading.main_thread().name}


def test_reads_the_reference_clip_from_the_repository(synthesiser: FakeSynthesiser) -> None:
    async def scenario() -> bool:
        async with smith_voice(synthesiser) as voice:
            return voice.has_voice("smith")

    assert asyncio.run(scenario())
    clip, transcript = synthesiser.voices["smith"]
    assert clip.is_file()
    assert transcript == SMITH.reference_line


def test_rejects_a_voice_without_a_clip(synthesiser: FakeSynthesiser) -> None:
    async def scenario() -> None:
        async with VoiceService(synthesiser) as voice:
            with pytest.raises(ValueError, match="no reference clip"):
                await voice.add_voice("smith", SMITH.model_copy(update={"reference_clip": None}))
            assert not voice.has_voice("smith")

    asyncio.run(scenario())


def test_refuses_an_npc_without_a_voice(synthesiser: FakeSynthesiser) -> None:
    async def scenario() -> None:
        async with smith_voice(synthesiser) as voice:
            with pytest.raises(KeyError, match="baker"):
                voice.speak("baker", "Fresh bread!")

    asyncio.run(scenario())


def test_speaks_the_players_conversation_first_then_in_order(
    synthesiser: FakeSynthesiser,
) -> None:
    gate = synthesiser.gate("Speaking.")

    async def scenario() -> None:
        async with smith_voice(synthesiser) as voice:
            speaking = asyncio.create_task(collect(voice.speak("smith", "Speaking.")))
            await until(lambda: synthesiser.started == ["Speaking."])
            queued = [
                asyncio.create_task(collect(voice.speak("smith", sentence, priority)))
                for sentence, priority in [
                    ("Overheard 1.", Priority.OVERHEARD),
                    ("Player 1.", Priority.PLAYER),
                    ("Overheard 2.", Priority.OVERHEARD),
                    ("Player 2.", Priority.PLAYER),
                ]
            ]
            await asyncio.sleep(0.01)
            assert synthesiser.started == ["Speaking."]
            gate.release(synthesiser.chunks)
            await asyncio.gather(speaking, *queued)

    asyncio.run(scenario())

    assert synthesiser.started == [
        "Speaking.",
        "Player 1.",
        "Player 2.",
        "Overheard 1.",
        "Overheard 2.",
    ]


def test_closing_a_sentence_stops_generating_it(synthesiser: FakeSynthesiser) -> None:
    gate = synthesiser.gate("Long.")

    async def scenario() -> list[bytes]:
        async with smith_voice(synthesiser) as voice:
            speech = voice.speak("smith", "Long.")
            gate.release()
            assert await anext(speech) == synthesiser.chunk(0)
            await speech.aclose()
            gate.release(synthesiser.chunks)
            return await collect(voice.speak("smith", "Next."))

    assert asyncio.run(scenario()) == all_chunks(synthesiser)
    assert synthesiser.made["Long."] == 2
    assert "Long." in synthesiser.closed


def test_a_sentence_cancelled_while_queued_never_starts(synthesiser: FakeSynthesiser) -> None:
    gate = synthesiser.gate("Speaking.")

    async def scenario() -> None:
        async with smith_voice(synthesiser) as voice:
            speaking = asyncio.create_task(collect(voice.speak("smith", "Speaking.")))
            await until(lambda: synthesiser.started == ["Speaking."])
            queued = asyncio.create_task(collect(voice.speak("smith", "Queued.")))
            await asyncio.sleep(0)
            queued.cancel()
            gate.release(synthesiser.chunks)
            await speaking
            await collect(voice.speak("smith", "After."))

    asyncio.run(scenario())

    assert synthesiser.started == ["Speaking.", "After."]


def test_a_failed_sentence_raises_and_the_next_one_plays(synthesiser: FakeSynthesiser) -> None:
    synthesiser.failing.add("Boom.")

    async def scenario() -> list[bytes]:
        async with smith_voice(synthesiser) as voice:
            with pytest.raises(RuntimeError, match="Boom"):
                await collect(voice.speak("smith", "Boom."))
            return await collect(voice.speak("smith", "After."))

    assert asyncio.run(scenario()) == all_chunks(synthesiser)


def test_stopping_ends_every_sentence(synthesiser: FakeSynthesiser) -> None:
    synthesiser.gate("Speaking.")

    async def scenario() -> list[list[bytes]]:
        async with smith_voice(synthesiser) as voice:
            speaking = asyncio.create_task(collect(voice.speak("smith", "Speaking.")))
            await until(lambda: synthesiser.started == ["Speaking."])
            queued = asyncio.create_task(collect(voice.speak("smith", "Queued.")))
            await asyncio.sleep(0)
        return await asyncio.gather(speaking, queued)

    assert asyncio.run(scenario()) == [[], []]
    assert synthesiser.started == ["Speaking."]


def test_speaking_after_stopping_raises(synthesiser: FakeSynthesiser) -> None:
    async def scenario() -> None:
        async with smith_voice(synthesiser) as voice:
            speech = voice.speak("smith", "Too late.")
        with pytest.raises(RuntimeError, match="isn't running"):
            async with asyncio.timeout(2):
                await collect(speech)

    asyncio.run(scenario())


def test_a_failed_load_stops_the_voice_thread(synthesiser: FakeSynthesiser) -> None:
    threads: list[threading.Thread] = []

    def load() -> None:
        threads.append(threading.current_thread())
        raise OSError("no model")

    synthesiser.load = load  # type: ignore[method-assign]
    voice = VoiceService(synthesiser)

    async def scenario() -> None:
        with pytest.raises(OSError, match="no model"):
            async with voice:
                pass

    asyncio.run(scenario())

    threads[0].join(timeout=2)
    assert not threads[0].is_alive()


class Hesitant(FakeSynthesiser):
    """Sends nothing for `steps` 50 ms steps, like Qwen while the trim holds a silent start."""

    def __init__(self, steps: int) -> None:
        super().__init__()
        self.steps = steps

    def generate(self, npc_id: str, sentence: str) -> Generator[bytes, None, None]:
        self.started.append(sentence)
        try:
            for _ in range(self.steps):
                time.sleep(0.05)
                yield b""
            yield self.chunk(0)
        finally:
            self.closed.append(sentence)


def test_empty_chunks_are_not_passed_on() -> None:
    async def scenario() -> list[bytes]:
        async with smith_voice(Hesitant(steps=3)) as voice:
            return await collect(voice.speak("smith", "Hm."))

    assert asyncio.run(scenario()) == [FakeSynthesiser.chunk(0)]


def test_a_sentence_stops_promptly_while_it_has_nothing_to_send_yet() -> None:
    synthesiser = Hesitant(steps=40)

    async def scenario() -> float:
        async with smith_voice(synthesiser) as voice:
            speaking = asyncio.create_task(collect(voice.speak("smith", "Overheard.")))
            await until(lambda: synthesiser.started == ["Overheard."])
            await asyncio.sleep(0.1)
            speaking.cancel()
            cancelled = time.perf_counter()
            await until(lambda: synthesiser.closed == ["Overheard."])
            return time.perf_counter() - cancelled

    assert asyncio.run(scenario()) < 0.2
