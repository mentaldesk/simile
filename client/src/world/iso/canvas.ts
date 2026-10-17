import type { Viewport } from '../view';
import type { IsoTile } from './manifest';
import { MAX_TILES_ACROSS } from './tuning';

export type NativeCanvas = { width: number; height: number; zoom: number };

export function nativeCanvas({ innerWidth, innerHeight, devicePixelRatio }: Viewport): NativeCanvas {
  return {
    width: Math.max(1, Math.floor(innerWidth * devicePixelRatio)),
    height: Math.max(1, Math.floor(innerHeight * devicePixelRatio)),
    zoom: 1 / devicePixelRatio,
  };
}

/** Whole device pixels per art pixel: the pixel ratio, or more to keep the view near the cap. */
export function isoZoom(canvasWidth: number, devicePixelRatio: number, tile: IsoTile): number {
  const capped = Math.round(canvasWidth / (MAX_TILES_ACROSS * tile.width));
  return Math.max(1, Math.round(devicePixelRatio), capped);
}
