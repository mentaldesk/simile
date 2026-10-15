import { expect, it } from 'vitest';
import { toFloat32 } from './pcm';

it('scales 16-bit PCM to -1..1', () => {
  expect(Array.from(toFloat32(Int16Array.of(0, 16384, -16384, -32768, 32767)))).toEqual([
    0,
    0.5,
    -0.5,
    -1,
    32767 / 32768,
  ]);
});

it('decodes an empty chunk to no samples', () => {
  expect(toFloat32(new Int16Array(0))).toHaveLength(0);
});
