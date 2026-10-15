import struct

import pytest

from simile.protocol import AudioChunk

# The same bytes are checked by client/src/net/audio.test.ts.
EXAMPLE = AudioChunk(line_id=7, sequence=2, pcm=struct.pack("<3h", 1, -2, 32767), last=True)
EXAMPLE_FRAME = bytes.fromhex("07000000 02000000 01000000 0100 feff ff7f")


def test_encodes_the_documented_layout() -> None:
    assert EXAMPLE.encode() == EXAMPLE_FRAME


def test_decodes_the_documented_layout() -> None:
    assert AudioChunk.decode(EXAMPLE_FRAME) == EXAMPLE


def test_round_trips_a_chunk_that_is_not_last() -> None:
    chunk = AudioChunk(line_id=2**32 - 1, sequence=0, pcm=b"\x00\x80" * 480)

    assert AudioChunk.decode(chunk.encode()) == chunk


def test_a_header_alone_is_an_empty_chunk() -> None:
    assert AudioChunk.decode(EXAMPLE_FRAME[:12]) == AudioChunk(7, 2, b"", last=True)


def test_rejects_half_a_sample() -> None:
    with pytest.raises(ValueError, match="16-bit"):
        AudioChunk(line_id=1, sequence=0, pcm=b"\x00")


def test_rejects_a_frame_shorter_than_the_header() -> None:
    with pytest.raises(ValueError, match="header"):
        AudioChunk.decode(b"\x01\x00\x00\x00")


def test_rejects_a_line_id_that_does_not_fit() -> None:
    with pytest.raises(struct.error):
        AudioChunk(line_id=2**32, sequence=0, pcm=b"").encode()
