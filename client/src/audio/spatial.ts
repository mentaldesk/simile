import type { Position } from '../net';

/** A voice's volume (0 to 1) and stereo pan (-1 left to 1 right). */
export type Mix = { gain: number; pan: number };

export const FULL_VOLUME_WITHIN = 2;
/** Tiles: the server's `out_of_earshot`, checked by server/tests/voicing/test_client_earshot.py. */
export const SILENT_BEYOND = 5.5;
export const OVERHEARD_GAIN = 1 / 3;
const MAX_PAN = 0.8;
const PARTNER_MAX_PAN = 0.3;

export const UNPOSITIONED: Mix = { gain: 1, pan: 0 };

function panning(listener: Position, source: Position, maxPan: number) {
  const dx = source.x - listener.x;
  const distance = Math.hypot(dx, source.y - listener.y);
  return { distance, pan: (maxPan * dx) / Math.max(distance, FULL_VOLUME_WITHIN) };
}

export function partnerMix(listener: Position, source: Position): Mix {
  return { gain: 1, pan: panning(listener, source, PARTNER_MAX_PAN).pan };
}

export function overheardMix(listener: Position, source: Position): Mix {
  const { distance, pan } = panning(listener, source, MAX_PAN);
  const fade = (SILENT_BEYOND - distance) / (SILENT_BEYOND - FULL_VOLUME_WITHIN);
  return { gain: OVERHEARD_GAIN * Math.min(1, Math.max(0, fade)) ** 2, pan };
}
