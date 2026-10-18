import type { Facing, Pose, Position } from '../../net';
import { objectsOf, propertyOf, type Tile, type TiledMap } from '../map';
import type { Point } from '../view';
import type { Figure } from './cutaway';
import { facingFor, standingFrame, type IsoFacing } from './sheets';
import { SITTING_NEARER } from './tuning';

/** The server's facings as A1's eight views. */
export const ISO_FACING: Record<Facing, IsoFacing> = {
  east: 'down_right',
  south_east: 'down',
  south: 'down_left',
  south_west: 'left',
  west: 'up_left',
  north_west: 'up',
  north: 'up_right',
  north_east: 'right',
};

/** Drawn only in the three-quarter views, the way spots face. */
export const POSES: readonly Pose[] = ['sitting', 'reading', 'working', 'looking'];

const THREE_QUARTER: ReadonlySet<IsoFacing> = new Set(['down_left', 'down_right', 'up_left', 'up_right']);

export const posed = (pose: Pose | undefined): pose is Pose => pose !== undefined && POSES.includes(pose);

/** A1's frame for someone still: in a pose, or standing, with their weight shifted or not. */
export function stillFrame(facing: IsoFacing, pose: Pose = 'standing', shifted = false): string {
  const shift = shifted ? '-shift' : '';
  if (posed(pose) && THREE_QUARTER.has(facing)) return `${facing}-${pose}${shift}`;
  return shifted ? `${facing}-standing-shift` : standingFrame(facing);
}

export const SPOTS_LAYER = 'spots';

/** Where a figure on a spot is drawn, from its tile's middle: tiles across and metres up. */
export type Seat = { x: number; y: number; z: number };

const NO_SEAT: Seat = { x: 0, y: 0, z: 0 };

const number = (value: unknown) => (typeof value === 'number' ? value : 0);

export function seatsOf(map: TiledMap): Map<string, Seat> {
  const size = map.tilewidth;
  return new Map(
    objectsOf(map, SPOTS_LAYER).map((spot) => [
      `${Math.round((spot.x ?? 0) / size)},${Math.round((spot.y ?? 0) / size)}`,
      { x: number(propertyOf(spot, 'dx')), y: number(propertyOf(spot, 'dy')), z: number(propertyOf(spot, 'dz')) },
    ]),
  );
}

export const seatAt = (seats: ReadonlyMap<string, Seat>, { x, y }: Tile): Seat | undefined =>
  seats.get(`${x},${y}`);

export type Posed = { readonly pose?: Pose; readonly facing?: Facing };

/** `nearer` is how many tiles nearer the camera they sort, in x and y. */
export type Still = { frame: string; facing: IsoFacing; seat: Seat; nearer: number };

export function stillFor(
  body: Posed,
  facing: IsoFacing,
  shifted: boolean,
  seat: Seat | undefined,
  toward?: Point,
): Still {
  const server = body.facing && ISO_FACING[body.facing];
  if (posed(body.pose)) {
    const way = server ?? facing;
    const nearer = body.pose === 'sitting' ? SITTING_NEARER : 0;
    return { frame: stillFrame(way, body.pose, shifted), facing: way, seat: seat ?? NO_SEAT, nearer };
  }
  const way = toward ? facingFor(toward, facing) : (server ?? facing);
  return { frame: stillFrame(way, 'standing', shifted), facing: way, seat: seat ?? NO_SEAT, nearer: 0 };
}

/** `drawn` is where the sprite goes, and `floor` and `at` where its shadows and light are. */
export type Placed = { at: Position; floor: Figure; drawn: Figure };

export function placed(
  position: Position,
  still: Still | undefined,
  figureAt: (position: Position) => Figure,
  pxPerMetreUp: number,
): Placed {
  const at = still ? { x: position.x + still.seat.x, y: position.y + still.seat.y } : position;
  const floor = figureAt(at);
  if (!still) return { at, floor, drawn: floor };
  const lift = still.seat.z * pxPerMetreUp;
  const depth = still.nearer ? figureAt({ x: at.x + still.nearer, y: at.y + still.nearer }).depth : floor.depth;
  return { at, floor, drawn: { x: floor.x, top: floor.top - lift, bottom: floor.bottom - lift, depth } };
}
