import type { Position } from '../net';
import { tilesApart } from '../ui/side-view';

/** A voice's volume (0 to 1) and stereo pan (-1 left to 1 right). */
export type Mix = { gain: number; pan: number };

export const FULL_VOLUME_WITHIN = 2;
/** Tiles: the server's `out_of_earshot`, checked by server/tests/voicing/test_client_earshot.py. */
export const SILENT_BEYOND = 6.5;
export const OVERHEARD_GAIN = 1 / 4;
const MAX_PAN = 0.8;
const PARTNER_MAX_PAN = 0.3;

export const UNPOSITIONED: Mix = { gain: 1, pan: 0 };

const panning = (listener: Position, source: Position, distance: number, maxPan: number) =>
  (maxPan * (source.x - listener.x)) / Math.max(distance, FULL_VOLUME_WITHIN);

const SILENT: Mix = { gain: 0, pan: 0 };

export function partnerMix(listener: Position, source: Position): Mix {
  const distance = tilesApart(listener, source);
  if (distance === undefined) return UNPOSITIONED;
  return { gain: 1, pan: panning(listener, source, distance, PARTNER_MAX_PAN) };
}

export function overheardMix(listener: Position, source: Position): Mix {
  const distance = tilesApart(listener, source);
  if (distance === undefined) return SILENT;
  const fade = (SILENT_BEYOND - distance) / (SILENT_BEYOND - FULL_VOLUME_WITHIN);
  const gain = OVERHEARD_GAIN * Math.min(1, Math.max(0, fade)) ** 2;
  return { gain, pan: panning(listener, source, distance, MAX_PAN) };
}
