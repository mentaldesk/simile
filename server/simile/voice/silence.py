import array
import math

from simile.protocol import SAMPLE_RATE

WINDOW = SAMPLE_RATE // 100
THRESHOLD = 15.0
"""RMS in 16-bit samples, about -67 dBFS: above Qwen's silence, below the start of a soft "f"."""
SUSTAINED = 3
"""10 ms windows in a row that a sound has to last, so a click isn't taken for speech."""
SKIP = 0.05
"""Seconds at the start never taken for speech, since Qwen sometimes opens with a click."""
LEAD_IN = 0.05
GIVE_UP = 1.5


class LeadingSilence:
    """Drops the silence a line starts with, holding its chunks back until the first sound."""

    def __init__(self) -> None:
        self._held = bytearray()
        self._found = False

    def feed(self, pcm: bytes) -> bytes:
        if self._found:
            return pcm
        self._held += pcm
        start = self._start()
        if start is None:
            return b""
        self._found = True
        return self._release(start)

    def end(self) -> bytes:
        """What's still held back once the line has ended."""
        self._found = True
        return self._release(0)

    def _release(self, sample: int) -> bytes:
        held, self._held = bytes(self._held[2 * sample :]), bytearray()
        return held

    def _start(self) -> int | None:
        samples = array.array("h", bytes(self._held[: len(self._held) // 2 * 2]))
        run = 0
        for window in range(round(SKIP * 100), len(samples) // WINDOW):
            chunk = samples[window * WINDOW : (window + 1) * WINDOW]
            loud = math.sqrt(sum(x * x for x in chunk) / WINDOW) >= THRESHOLD
            run = run + 1 if loud else 0
            if run == SUSTAINED:
                onset = (window - SUSTAINED + 1) * WINDOW
                return max(0, onset - round(LEAD_IN * SAMPLE_RATE))
        return 0 if len(samples) >= GIVE_UP * SAMPLE_RATE else None
