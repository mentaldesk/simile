import type { Point, Size } from '../view';
import type { IsoTile } from './manifest';
import { project, unproject } from './projection';

/** How far from the view's centre the target may sit, as a share of the half view. */
export const TARGET_REACH = 0.75;

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max);
const clampOrCentre = (value: number, margin: number, size: number) =>
  2 * margin >= size ? size / 2 : clamp(value, margin, size - margin);

/** Centres on the target, keeping the view on the map's diamond unless the target would leave reach. */
export function isoScroll(target: Point, view: Size, map: Size, tile: IsoTile, zoom: number): Point {
  const half = { x: view.width / zoom / 2, y: view.height / zoom / 2 };
  const margin = half.x / tile.width + half.y / tile.height;
  const ground = unproject(tile, target);
  const centre = project(tile, {
    x: clampOrCentre(ground.x, margin, map.width),
    y: clampOrCentre(ground.y, margin, map.height),
  });
  const reach = { x: half.x * TARGET_REACH, y: half.y * TARGET_REACH };
  return {
    x: Math.round(clamp(centre.x, target.x - reach.x, target.x + reach.x)) - view.width / 2,
    y: Math.round(clamp(centre.y, target.y - reach.y, target.y + reach.y)) - view.height / 2,
  };
}
