import { imageOrigin, sliceAt } from './depth';
import type { IsoTile, SceneryObject } from './manifest';
import { project } from './projection';

export const CUTAWAY_ALPHA = 0.3;
export const CUTAWAY_SECONDS = 0.2;

/** A standing figure on screen: the vertical line from its head to its feet, and its depth. */
export type Figure = { x: number; top: number; bottom: number; depth: number };

/** Whether a building is in front where the figure stands, and its silhouette covers part of it. */
export function hides(building: SceneryObject, figure: Figure, tile: IsoTile): boolean {
  const slice = sliceAt(building, figure.x, tile);
  if (!slice || slice.depth <= figure.depth) return false;
  const [x0, y0, x1, y1] = building.footprint;
  const back = project(tile, { x: x0, y: y0 });
  const front = project(tile, { x: x1, y: y1 });
  const slope = tile.height / tile.width;
  const roof = imageOrigin(building, tile).y + Math.abs(figure.x - back.x) * slope;
  const base = front.y - Math.abs(figure.x - front.x) * slope;
  return figure.top < base && figure.bottom > roof;
}

/** Moves an alpha toward its target, over `CUTAWAY_SECONDS` for the whole fade. */
export function fade(alpha: number, target: number, dt: number): number {
  const step = ((1 - CUTAWAY_ALPHA) * dt) / CUTAWAY_SECONDS;
  return alpha < target ? Math.min(target, alpha + step) : Math.max(target, alpha - step);
}
