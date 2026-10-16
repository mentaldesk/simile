import array
import math

import pytest

from simile.protocol import SAMPLE_RATE
from simile.voice.silence import GIVE_UP, LEAD_IN, LeadingSilence


def silence(seconds: float, level: int = 2) -> bytes:
    """Near silence, like Qwen's: a tiny square wave."""
    n = round(seconds * SAMPLE_RATE)
    return array.array("h", (level if i % 2 else -level for i in range(n))).tobytes()


def tone(seconds: float, amplitude: float = 8000, fade_in: float = 0.0) -> bytes:
    n = round(seconds * SAMPLE_RATE)
    ramp = max(1, round(fade_in * SAMPLE_RATE))
    return array.array(
        "h",
        (
            round(
                amplitude * min(1.0, (i + 1) / ramp) * math.sin(2 * math.pi * 220 * i / SAMPLE_RATE)
            )
            for i in range(n)
        ),
    ).tobytes()


def trimmed(pcm: bytes, chunk: float = 0.25) -> bytes:
    size = round(chunk * SAMPLE_RATE) * 2
    trim = LeadingSilence()
    out = b"".join(trim.feed(pcm[i : i + size]) for i in range(0, len(pcm), size))
    return out + trim.end()


def seconds(pcm: bytes) -> float:
    return len(pcm) / 2 / SAMPLE_RATE


def test_drops_the_silence_before_the_first_sound_but_a_short_lead_in() -> None:
    speech = tone(1.0)

    out = trimmed(silence(0.4) + speech)

    assert out.endswith(speech)
    assert seconds(out) == pytest.approx(1.0 + LEAD_IN, abs=0.011)


def test_drops_a_click_at_the_start_and_a_blip_in_the_silence() -> None:
    click, blip, speech = tone(0.03, 20000), tone(0.02, 20000), tone(1.0)

    out = trimmed(click + silence(0.3) + blip + silence(0.2) + speech)

    assert out.endswith(speech)
    assert seconds(out) == pytest.approx(1.0 + LEAD_IN, abs=0.011)


def test_keeps_a_quiet_start() -> None:
    speech = tone(0.1, amplitude=25) + tone(0.9, fade_in=0.2)

    out = trimmed(silence(0.4) + speech)

    assert out.endswith(speech)
    assert seconds(out) == pytest.approx(1.0 + LEAD_IN, abs=0.011)


def test_leaves_a_line_that_starts_at_once_or_never_gets_loud() -> None:
    at_once = tone(1.0)
    quiet = silence(0.8, level=10)
    long_silence = silence(GIVE_UP + 0.1) + tone(0.5)

    assert trimmed(at_once) == at_once
    assert trimmed(quiet) == quiet
    assert trimmed(long_silence) == long_silence


def test_holds_chunks_until_it_hears_the_first_sound() -> None:
    trim = LeadingSilence()

    assert trim.feed(silence(0.25)) == b""
    assert trim.feed(silence(0.15) + tone(0.1)) != b""
    assert trim.feed(tone(0.25)) == tone(0.25)


@pytest.mark.parametrize("chunk", [0.01, 0.0731, 0.25, 2.0])
def test_trims_the_same_however_the_audio_is_chunked(chunk: float) -> None:
    pcm = tone(0.02, 20000) + silence(0.37) + tone(0.6, fade_in=0.1)

    assert trimmed(pcm, chunk) == trimmed(pcm, 2.0)
