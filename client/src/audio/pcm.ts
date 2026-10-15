export function toFloat32(samples: Int16Array): Float32Array<ArrayBuffer> {
  return Float32Array.from(samples, (sample) => sample / 32768);
}
