import { expect, it } from 'vitest';
import { encodeWav, uploadProblem } from './wav';

it('writes mono 16-bit PCM WAV', () => {
  const bytes = encodeWav([new Float32Array([0, 1, -1]), new Float32Array([0.5, 2])], 48000);
  const view = new DataView(bytes.buffer);
  const text = (offset: number) => String.fromCharCode(...bytes.slice(offset, offset + 4));
  expect([text(0), text(8), text(12), text(36)]).toEqual(['RIFF', 'WAVE', 'fmt ', 'data']);
  expect(view.getUint32(4, true)).toBe(36 + 10);
  expect(view.getUint16(20, true)).toBe(1);
  expect(view.getUint16(22, true)).toBe(1);
  expect(view.getUint32(24, true)).toBe(48000);
  expect(view.getUint32(28, true)).toBe(96000);
  expect(view.getUint16(34, true)).toBe(16);
  expect(view.getUint32(40, true)).toBe(10);
  const samples = [0, 1, 2, 3, 4].map((i) => view.getInt16(44 + i * 2, true));
  expect(samples).toEqual([0, 32767, -32768, 16383, 32767]);
  expect(bytes.length).toBe(54);
});

it('checks a file before it goes up', () => {
  expect(uploadProblem({ name: 'me.WAV', size: 1000 })).toBeNull();
  expect(uploadProblem({ name: 'me.m4a', size: 1000 })).toBeNull();
  expect(uploadProblem({ name: 'me.webm', size: 1000 })).toBe('Choose a WAV, MP3 or M4A file.');
  expect(uploadProblem({ name: 'me.mp3', size: 11 * 1024 * 1024 })).toBe(
    'That file is over 10 MB.',
  );
  expect(uploadProblem({ name: 'me.wav', size: 0 })).toBe('That file is empty.');
});
