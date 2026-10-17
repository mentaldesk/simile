import type { Viewport } from '../view';
import type { IsoTile } from './manifest';
import { MAX_TILES_ACROSS } from './tuning';

export type NativeCanvas = { width: number; height: number; zoom: number };

/** The window in device pixels, shown at 1 / devicePixelRatio so each canvas pixel is a device pixel. */
export function nativeCanvas({ innerWidth, innerHeight, devicePixelRatio }: Viewport): NativeCanvas {
  return {
    width: Math.max(1, Math.floor(innerWidth * devicePixelRatio)),
    height: Math.max(1, Math.floor(innerHeight * devicePixelRatio)),
    zoom: 1 / devicePixelRatio,
  };
}

/** Whole device pixels per art pixel: one per CSS pixel, more once the view would pass the cap. */
export function isoZoom(canvasWidth: number, devicePixelRatio: number, tile: IsoTile): number {
  const capped = Math.ceil(canvasWidth / (MAX_TILES_ACROSS * tile.width));
  return Math.max(1, Math.round(devicePixelRatio), capped);
}
