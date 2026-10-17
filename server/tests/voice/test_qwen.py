import array
import asyncio
import logging
import math
import struct
import time

import pytest

from simile.npc import load_npcs
from simile.protocol import SAMPLE_RATE
from simile.schema import Voice
from simile.voice import VoiceService
from simile.voice.service import REPO_ROOT
from simile.voice.silence import SKIP, LeadingSilence

pytestmark = pytest.mark.mlx

DWARF_SMITH = Voice(
    description="An old dwarf blacksmith with a deep, gravelly Scottish voice.",
    reference_line=(
        "Aye, I've been working this forge for nigh on fifty years. "
        "Iron doesn't lie to you, not like people do."
    ),
    reference_clip="voice-lab/voices/dwarf_smith.wav",
)
LINE = "The mines went quiet three winters ago. Nobody who went down to find out why came back up."


def test_converts_audio_to_16_bit_pcm() -> None:
    import mlx.core as mx

    from simile.voice.qwen import to_pcm

    pcm = to_pcm(mx.array([0.0, 0.5, -1.5, 1.0]))

    assert pcm == struct.pack("<4h", 0, 16384, -32767, 32767)


def test_streams_a_line_in_a_cloned_voice_faster_than_real_time() -> None:
    from simile.voice.qwen import QwenSynthesiser

    async def scenario() -> tuple[float, int, float]:
        async with VoiceService(QwenSynthesiser()) as voice:
            await voice.add_voice("dwarf_smith", DWARF_SMITH)
            started = time.perf_counter()
            first_audio = 0.0
            pcm = b""
            async for chunk in voice.speak("dwarf_smith", LINE):
                first_audio = first_audio or time.perf_counter() - started
                assert len(chunk) % 2 == 0
                pcm += chunk
            return first_audio, len(pcm) // 2, time.perf_counter() - started

    first_audio, samples, elapsed = asyncio.run(scenario())

    seconds = samples / SAMPLE_RATE
    assert 2 < seconds < 15
    assert first_audio < 0.5
    assert seconds / elapsed >= 2


def test_cancelling_stops_generation_promptly() -> None:
    from simile.voice.qwen import QwenSynthesiser

    async def scenario() -> float:
        async with VoiceService(QwenSynthesiser()) as voice:
            await voice.add_voice("dwarf_smith", DWARF_SMITH)
            speech = voice.speak("dwarf_smith", LINE)
            await anext(speech)
            await speech.aclose()
            cancelled = time.perf_counter()
            async for _ in voice.speak("dwarf_smith", "Aye."):
                return time.perf_counter() - cancelled
        raise AssertionError("no audio after cancelling")

    assert asyncio.run(scenario()) < 0.5


def test_warns_when_a_sentence_hits_the_generation_cap(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from simile.voice import qwen

    monkeypatch.setattr(qwen, "TOKENS_PER_SECOND", 1)

    async def scenario() -> None:
        async with VoiceService(qwen.QwenSynthesiser()) as voice:
            await voice.add_voice("dwarf_smith", DWARF_SMITH)
            async for _ in voice.speak("dwarf_smith", LINE):
                pass

    with caplog.at_level(logging.WARNING, logger="simile.voice.qwen"):
        asyncio.run(scenario())

    assert "Cut dwarf_smith off" in caplog.text


class Untrimmed:
    def feed(self, pcm: bytes) -> bytes:
        return pcm

    def end(self) -> bytes:
        return b""


def loudest(pcm: bytes) -> float:
    data = array.array("h", pcm)
    windows = range(0, len(data) - 239, 240)
    return max((math.sqrt(sum(x * x for x in data[i : i + 240]) / 240) for i in windows), default=0)


def test_drops_the_silence_a_line_starts_with_and_nothing_after_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from simile.voice import qwen

    tobias = next(npc for npc in load_npcs() if npc.id == "tobias")
    assert tobias.voice.reference_clip is not None
    synthesiser = qwen.QwenSynthesiser(seed=1)
    synthesiser.load()
    clip = REPO_ROOT / tobias.voice.reference_clip
    synthesiser.add_voice("tobias", clip, tobias.voice.reference_line)
    lines = ["Fair enough, I suppose.", "So, what brings you here?", "Honestly?"]

    trimmed = [b"".join(synthesiser.generate("tobias", line)) for line in lines]
    monkeypatch.setattr(qwen, "LeadingSilence", Untrimmed)
    whole = [b"".join(synthesiser.generate("tobias", line)) for line in lines]

    for raw, out in zip(whole, trimmed, strict=True):
        dropped = raw[: len(raw) - len(out)]
        assert raw.endswith(out)
        assert len(dropped) > 0.05 * SAMPLE_RATE * 2
        assert loudest(dropped[round(SKIP * SAMPLE_RATE) * 2 :]) < 250
        retrimmed = LeadingSilence()
        assert retrimmed.feed(out) + retrimmed.end() == out
