import { describe, expect, it } from 'vitest';
import { decodeAudioChunk, encodeAudioChunk, type AudioChunk } from './audio';

// The same bytes are checked by server/tests/protocol/test_audio.py.
const example: AudioChunk = {
  lineId: 7,
  sequence: 2,
  last: true,
  samples: Int16Array.of(1, -2, 32767),
};
const exampleFrame = '07000000' + '02000000' + '01000000' + '0100' + 'feff' + 'ff7f';

const hex = (buffer: ArrayBuffer) =>
  Array.from(new Uint8Array(buffer), (byte) => byte.toString(16).padStart(2, '0')).join('');
const bytes = (hex: string) =>
  Uint8Array.from(hex.match(/../g) ?? [], (pair) => parseInt(pair, 16)).buffer;

describe('audio chunks', () => {
  it('encode to the documented layout', () => {
    expect(hex(encodeAudioChunk(example))).toBe(exampleFrame);
  });

  it('decode from the documented layout', () => {
    expect(decodeAudioChunk(bytes(exampleFrame))).toEqual(example);
  });

  it('round-trip a chunk that is not last', () => {
    const chunk = { lineId: 2 ** 32 - 1, sequence: 0, last: false, samples: new Int16Array(480) };

    expect(decodeAudioChunk(encodeAudioChunk(chunk))).toEqual(chunk);
  });

  it('decode a header alone as an empty chunk', () => {
    expect(decodeAudioChunk(bytes(exampleFrame.slice(0, 24))).samples).toHaveLength(0);
  });

  it.each([4, 13])('reject a %i-byte frame', (length) => {
    expect(() => decodeAudioChunk(new ArrayBuffer(length))).toThrow('Not an audio chunk');
  });
});
