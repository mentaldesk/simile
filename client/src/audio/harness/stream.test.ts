import { describe, expect, it } from 'vitest';
import { decodeAudioChunk } from '../../net/audio';
import { toFloat32 } from '../pcm';
import { arrivalGaps, audioFrames, CHUNK_SAMPLES, toInt16 } from './stream';

describe('audioFrames', () => {
  it('splits a line into numbered chunks, marking only the last', () => {
    const samples = Int16Array.from({ length: 2.5 * CHUNK_SAMPLES }, (_, i) => i % 1000);

    const chunks = audioFrames(7, samples).map(decodeAudioChunk);

    expect(chunks.map(({ lineId, sequence, last }) => [lineId, sequence, last])).toEqual([
      [7, 0, false],
      [7, 1, false],
      [7, 2, true],
    ]);
    expect(chunks.flatMap((chunk) => Array.from(chunk.samples))).toEqual(Array.from(samples));
  });

  it('sends a line with no samples as one empty last chunk', () => {
    expect(audioFrames(7, new Int16Array(0)).map(decodeAudioChunk)).toEqual([
      { lineId: 7, sequence: 0, last: true, samples: new Int16Array(0) },
    ]);
  });
});

it('converts floats to 16-bit PCM, clipping out-of-range samples', () => {
  const pcm = Int16Array.of(0, 16384, -32768, 32767, -123);

  expect(toInt16(toFloat32(pcm))).toEqual(pcm);
  expect(Array.from(toInt16(Float32Array.of(1.5, -1.5)))).toEqual([32767, -32768]);
});

it('spaces chunks unevenly but ahead of real time', () => {
  const chunkSeconds = CHUNK_SAMPLES / 24_000;

  expect(arrivalGaps(3, () => 0)).toEqual([0.5, 0.5, 0.5].map((x) => x * chunkSeconds));
  for (const gap of arrivalGaps(100)) expect(gap).toBeLessThanOrEqual(chunkSeconds);
});
