import { imageOrigin, sliceAt } from './depth';
import type { IsoTile, SceneryObject } from './manifest';
import { project } from './projection';

export const CUTAWAY_ALPHA = 0.3;
export const CUTAWAY_SECONDS = 0.2;
export const CUTAWAY_HOLD_SECONDS = 0.3;

/** A standing figure on screen: the vertical line from its head to its feet, and its depth. */
export type Figure = { x: number; top: number; bottom: number; depth: number };

/** Whether a building is in front where the figure stands, and its silhouette covers part of it. */
export function hides(building: SceneryObject, figure: Figure, tile: IsoTile): boolean {
  const [x0, y0, x1, y1] = building.footprint;
  const left = project(tile, { x: x0, y: y1 }).x;
  const right = project(tile, { x: x1, y: y0 }).x;
  if (figure.x < left || figure.x > right) return false;
  const slice = sliceAt(building, figure.x, tile);
  if (!slice || slice.depth <= figure.depth) return false;
  const back = project(tile, { x: x0, y: y0 });
  const front = project(tile, { x: x1, y: y1 });
  const slope = tile.height / tile.width;
  const roof = imageOrigin(building, tile).y + Math.abs(figure.x - back.x) * slope;
  const base = front.y - Math.abs(figure.x - front.x) * slope;
  return figure.top < base && figure.bottom > roof;
}

/** A building's alpha: out while it hides the player, back in once it hasn't for a moment. */
export class Cutaway {
  alpha = 1;
  private sinceHidden = Infinity;

  update(hiding: boolean, dt: number): number {
    this.sinceHidden = hiding ? 0 : this.sinceHidden + dt;
    const target = this.sinceHidden < CUTAWAY_HOLD_SECONDS ? CUTAWAY_ALPHA : 1;
    const step = ((1 - CUTAWAY_ALPHA) * dt) / CUTAWAY_SECONDS;
    this.alpha =
      this.alpha < target ? Math.min(target, this.alpha + step) : Math.max(target, this.alpha - step);
    return this.alpha;
  }
}
