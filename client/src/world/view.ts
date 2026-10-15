import type { Position } from '../net';
import { TILE_SIZE } from './tuning';

export type Point = { x: number; y: number };
export type Size = { width: number; height: number };

/** The bottom centre of an entity's tile in whole world pixels: where its sprite's feet go. */
export function feetOf({ x, y }: Position): Point {
  return { x: Math.round((x + 0.5) * TILE_SIZE), y: Math.round((y + 1) * TILE_SIZE) };
}

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max);

function centreOn(target: number, view: number, world: number, zoom: number): number {
  const half = view / zoom / 2;
  const centre =
    world <= 2 * half
      ? Math.round(world / 2)
      : clamp(Math.round(target), Math.ceil(half), Math.floor(world - half));
  return centre - view / 2;
}

/** Centres the view on a whole world pixel, so each art pixel is exactly `zoom` canvas pixels. */
export function followScroll(target: Point, view: Size, world: Size, zoom: number): Point {
  return {
    x: centreOn(target.x, view.width, world.width, zoom),
    y: centreOn(target.y, view.height, world.height, zoom),
  };
}

/** Where a world point is drawn on the canvas, for a camera at `scroll` zoomed about its centre. */
export function toCanvas(point: Point, scroll: Point, view: Size, zoom: number): Point {
  return {
    x: (point.x - scroll.x - view.width / 2) * zoom + view.width / 2,
    y: (point.y - scroll.y - view.height / 2) * zoom + view.height / 2,
  };
}
