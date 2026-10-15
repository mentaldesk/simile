import { SAMPLE_RATE } from '../../net';
import { encodeAudioChunk } from '../../net/audio';

export const CHUNK_SAMPLES = SAMPLE_RATE / 10;

export function toInt16(samples: Float32Array): Int16Array {
  return Int16Array.from(samples, (sample) =>
    Math.max(-32768, Math.min(32767, Math.round(sample * 32768))),
  );
}

export function audioFrames(
  lineId: number,
  samples: Int16Array,
  size = CHUNK_SAMPLES,
): ArrayBuffer[] {
  const count = Math.max(1, Math.ceil(samples.length / size));
  return Array.from({ length: count }, (_, sequence) =>
    encodeAudioChunk({
      lineId,
      sequence,
      last: sequence === count - 1,
      samples: samples.subarray(sequence * size, (sequence + 1) * size),
    }),
  );
}

/** Seconds between chunks: unevenly spaced but ahead of real time, like the TTS. */
export function arrivalGaps(count: number, random = Math.random): number[] {
  return Array.from({ length: count }, () => (CHUNK_SAMPLES / SAMPLE_RATE) * (0.5 + random() / 2));
}
