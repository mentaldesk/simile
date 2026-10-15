import type { Position } from '../net';

/** A voice's volume (0 to 1) and stereo pan (-1 left to 1 right). */
export type Mix = { gain: number; pan: number };

export const FULL_VOLUME_WITHIN = 2;
/** Tiles. Keep it at or beyond the server's earshot, so voices fade out before they're cut. */
export const SILENT_BEYOND = 14;
const MAX_PAN = 0.8;

export const UNPOSITIONED: Mix = { gain: 1, pan: 0 };

export function spatialMix(listener: Position, source: Position): Mix {
  const dx = source.x - listener.x;
  const distance = Math.hypot(dx, source.y - listener.y);
  const fade = (SILENT_BEYOND - distance) / (SILENT_BEYOND - FULL_VOLUME_WITHIN);
  return {
    gain: Math.min(1, Math.max(0, fade)) ** 2,
    pan: (MAX_PAN * dx) / Math.max(distance, FULL_VOLUME_WITHIN),
  };
}
