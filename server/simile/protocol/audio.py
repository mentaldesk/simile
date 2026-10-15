import struct
from dataclasses import dataclass
from typing import Self

SAMPLE_RATE = 24_000
HEADER = struct.Struct("<IIB3x")
LAST = 0x01


@dataclass(frozen=True)
class AudioChunk:
    """Part of a line's audio: 24 kHz mono 16-bit little-endian PCM. See docs/protocol.md."""

    line_id: int
    sequence: int
    pcm: bytes
    last: bool = False

    def __post_init__(self) -> None:
        if len(self.pcm) % 2:
            raise ValueError("pcm must be whole 16-bit samples")

    def encode(self) -> bytes:
        return HEADER.pack(self.line_id, self.sequence, LAST if self.last else 0) + self.pcm

    @classmethod
    def decode(cls, frame: bytes) -> Self:
        if len(frame) < HEADER.size:
            raise ValueError(f"an audio chunk needs a {HEADER.size}-byte header")
        line_id, sequence, flags = HEADER.unpack_from(frame)
        return cls(line_id, sequence, frame[HEADER.size :], bool(flags & LAST))
