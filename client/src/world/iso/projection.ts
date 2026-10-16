import type { Position } from '../../net';
import type { Point } from '../view';
import type { IsoTile } from './manifest';

/** Map point in tiles, `z` metres up, to screen px, with tile (0, 0)'s top corner at the origin. */
export function project(tile: IsoTile, { x, y }: Point, z = 0): Point {
  return {
    x: ((x - y) * tile.width) / 2,
    y: ((x + y) * tile.height) / 2 - z * tile.px_per_metre_up,
  };
}

export function unproject(tile: IsoTile, { x, y }: Point): Point {
  return { x: x / tile.width + y / tile.height, y: y / tile.height - x / tile.width };
}

/** An entity on tile (x, y) stands at its centre. */
export const feetOf = ({ x, y }: Position): Point => ({ x: x + 0.5, y: y + 0.5 });
