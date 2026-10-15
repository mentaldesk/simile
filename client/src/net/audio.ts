export const SAMPLE_RATE = 24_000;

const HEADER_BYTES = 12;
const LAST = 0x01;

/** Part of a line's audio: 24 kHz mono 16-bit PCM. The layout is in docs/protocol.md. */
export type AudioChunk = {
  lineId: number;
  sequence: number;
  last: boolean;
  samples: Int16Array;
};

export function decodeAudioChunk(frame: ArrayBuffer): AudioChunk {
  if (frame.byteLength < HEADER_BYTES || frame.byteLength % 2) {
    throw new Error(`Not an audio chunk: ${frame.byteLength} bytes`);
  }
  const header = new DataView(frame, 0, HEADER_BYTES);
  return {
    lineId: header.getUint32(0, true),
    sequence: header.getUint32(4, true),
    last: (header.getUint8(8) & LAST) !== 0,
    samples: new Int16Array(frame, HEADER_BYTES),
  };
}

export function encodeAudioChunk(chunk: AudioChunk): ArrayBuffer {
  const frame = new ArrayBuffer(HEADER_BYTES + chunk.samples.byteLength);
  const header = new DataView(frame, 0, HEADER_BYTES);
  header.setUint32(0, chunk.lineId, true);
  header.setUint32(4, chunk.sequence, true);
  header.setUint8(8, chunk.last ? LAST : 0);
  new Int16Array(frame, HEADER_BYTES).set(chunk.samples);
  return frame;
}
