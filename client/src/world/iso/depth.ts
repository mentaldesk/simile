import type { Point } from '../view';
import type { IsoTile, SceneryObject, Slice } from './manifest';
import { project } from './projection';

export const GROUND_DEPTH = -1e6;

/** Above any slice keyed at the same screen y: on a tie the resident is in front. */
const RESIDENT_TIE = 1e-3;

/** A resident sorts by the screen y of their feet on the ground plane. */
export const residentDepth = (feet: Point, tile: IsoTile): number =>
  project(tile, feet).y + RESIDENT_TIE;

export const imageOrigin = (object: SceneryObject, tile: IsoTile): Point => {
  const anchor = project(tile, { x: object.anchor[0], y: object.anchor[1] });
  return { x: anchor.x + object.offset[0], y: anchor.y + object.offset[1] };
};

export type SliceDraw = { x: number; y: number; cropX: number; cropWidth: number; depth: number };

export function sliceDraws(object: SceneryObject, tile: IsoTile): SliceDraw[] {
  const origin = imageOrigin(object, tile);
  return object.slices.map(({ x, width, depth }) => ({ ...origin, cropX: x, cropWidth: width, depth }));
}

export function sliceAt(object: SceneryObject, screenX: number, tile: IsoTile): Slice | undefined {
  const x = screenX - imageOrigin(object, tile).x;
  return object.slices.find((slice) => x >= slice.x && x < slice.x + slice.width);
}
