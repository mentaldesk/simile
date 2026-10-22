"""Says greetings in a cloned voice. Jobs run it as a script, so it can't import simile."""

import argparse
import json
import subprocess
import sys
import tempfile
import wave
import zlib
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any

MODEL = "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-8bit"
SAMPLE_RATE = 24_000
BITRATE = 32_000
WINDOW = SAMPLE_RATE // 100
THRESHOLD = 10 ** (-48 / 20)
"""A 10 ms window this loud next to the greeting's peak, -48 dB, counts as sound."""
SUSTAINED = 3
SKIP = 0.05
"""Seconds at the start never taken for speech, since Qwen sometimes opens with a click."""
LEAD_IN = 0.04
TAIL = 0.12
FADE = 0.015
LONGEST = 3.0

type Progress = Callable[[float, str], None]


def seed(take: int, voice: str, text: str) -> int:
    """As V1 seeds a sentence, so a take always comes out the same."""
    return zlib.crc32(f"{take}/{voice}/{text}".encode())


def load(model: str = MODEL) -> Any:
    from mlx_audio.tts.utils import load_model

    return load_model(model)


def say(model: Any, reference: Any, transcript: str, text: str, seed: int) -> Any:
    """One greeting as float samples at 24 kHz, without the silence around it."""
    import mlx.core as mx
    import numpy as np

    mx.random.seed(seed)
    chunks = [
        np.array(result.audio, dtype=np.float32)
        for result in model.generate(
            text=text,
            lang_code="english",
            ref_audio=reference,
            ref_text=transcript,
            max_tokens=round(12.5 * (LONGEST + 1)),
        )
    ]
    return trimmed(np.concatenate(chunks))


def trimmed(audio: Any) -> Any:
    """Drops the silence before and after the speech, with short fades at the cuts."""
    import numpy as np

    windows = len(audio) // WINDOW
    if not windows:
        return audio
    framed = audio[: windows * WINDOW].reshape(windows, WINDOW)
    rms = np.sqrt((framed**2).mean(axis=1))
    loud = rms >= THRESHOLD * max(float(np.abs(audio).max()), 1e-6)
    loud[: round(SKIP * 100)] = False
    runs = np.convolve(loud.astype(int), np.ones(SUSTAINED, dtype=int), mode="valid")
    sustained = np.flatnonzero(runs == SUSTAINED)
    if not len(sustained):
        return audio
    first = sustained[0] * WINDOW
    last = (sustained[-1] + SUSTAINED) * WINDOW
    start = max(0, first - round(LEAD_IN * SAMPLE_RATE))
    end = min(len(audio), last + round(TAIL * SAMPLE_RATE))
    cut = audio[start:end].copy()
    fade = min(round(FADE * SAMPLE_RATE), len(cut) // 2)
    if fade:
        ramp = np.linspace(0, 1, fade, dtype=np.float32)
        cut[:fade] *= ramp
        cut[-fade:] *= ramp[::-1]
    return cut


def write_wav(audio: Any, path: Path) -> None:
    import numpy as np

    pcm = (np.clip(audio, -1, 1) * 32767).round().astype("<i2")
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes(pcm.tobytes())


def encode(audio: Any, path: Path) -> None:
    """AAC in an m4a, which every browser decodes. afconvert comes with macOS."""
    with tempfile.TemporaryDirectory() as scratch:
        wav = Path(scratch) / "greeting.wav"
        write_wav(audio, wav)
        aac = Path(scratch) / "greeting.m4a"
        subprocess.run(
            ["afconvert", "-f", "m4af", "-d", "aac", "-b", str(BITRATE), str(wav), str(aac)],
            check=True,
            capture_output=True,
        )
        aac.replace(path)


def speak(
    model: Any,
    voice: str,
    clip: Path,
    transcript: str,
    lines: Sequence[tuple[str, int]],
    out: Path,
    progress: Progress | None = None,
) -> list[float]:
    """Writes `<voice>_<n>.m4a` in `out` for each (text, take), and returns their lengths."""
    from mlx_audio.utils import load_audio

    reference = load_audio(str(clip), sample_rate=model.sample_rate)
    seconds = []
    for n, (text, take) in enumerate(lines, 1):
        if progress:
            progress((n - 1) / len(lines), f"Saying greeting {n} of {len(lines)}")
        audio = say(model, reference, transcript, text, seed(take, voice, text))
        encode(audio, out / f"{voice}_{n}.m4a")
        seconds.append(round(len(audio) / SAMPLE_RATE, 2))
    return seconds


def report(fraction: float, message: str) -> None:
    print("JOB " + json.dumps({"progress": fraction, "message": message}), flush=True)


def main(argv: Iterable[str] | None = None) -> None:
    """The greetings job: reads `greetings.json` in its work directory and writes beside it."""
    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("work", type=Path)
    work = parser.parse_args(None if argv is None else list(argv)).work
    asked = json.loads((work / "greetings.json").read_text(encoding="utf-8"))
    report(0.0, "Loading the voice model")
    model = load()
    lines = [(text, 0) for text in asked["lines"]]
    seconds = speak(
        model, asked["voice"], Path(asked["clip"]), asked["transcript"], lines, work, report
    )
    (work / "spoken.json").write_text(json.dumps({"seconds": seconds}), encoding="utf-8")
    report(1.0, "Said")


if __name__ == "__main__":
    sys.exit(main())
