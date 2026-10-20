import type { Viewport } from './view';

export type NativeCanvas = { width: number; height: number; zoom: number };

export function nativeCanvas({ innerWidth, innerHeight, devicePixelRatio }: Viewport): NativeCanvas {
  return {
    width: Math.max(1, Math.floor(innerWidth * devicePixelRatio)),
    height: Math.max(1, Math.floor(innerHeight * devicePixelRatio)),
    zoom: 1 / devicePixelRatio,
  };
}
