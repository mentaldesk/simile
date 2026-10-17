import { WALKING_SPEED } from '../tuning';
import type { Point } from '../view';
import type { SpriteFrame } from './screen';

export type IsoFacing =
  | 'down_right'
  | 'down'
  | 'down_left'
  | 'left'
  | 'up_left'
  | 'up'
  | 'up_right'
  | 'right';

/** By the angle of a step on the map, x east and y south, from east round through south. */
export const ISO_FACINGS: readonly IsoFacing[] = [
  'down_right',
  'down',
  'down_left',
  'left',
  'up_left',
  'up',
  'up_right',
  'right',
];

export const PIXEL_TEXTURE = { width: 16, height: 24 };

/** Scene px per texture px: a 24 px figure 96 px tall, 1.8 m by the scenery's scale. */
export const PIXEL_SCALE = 4;

const WALK_COLUMNS = [0, 1, 2, 1];
const STANDING_COLUMN = 1;

export function facingFor(step: Point, previous: IsoFacing): IsoFacing {
  if (step.x === 0 && step.y === 0) return previous;
  const eighths = Math.round(Math.atan2(step.y, step.x) / (Math.PI / 4));
  return ISO_FACINGS[(eighths + 8) % 8];
}

export function pixelFrame(scale: number = PIXEL_SCALE, texture = PIXEL_TEXTURE): SpriteFrame {
  if (!Number.isInteger(scale) || scale < 1) throw new RangeError(`scale ${scale} isn't a whole number`);
  const [width, height] = [texture.width * scale, texture.height * scale];
  return { width, height, anchor: { x: width / 2, y: height }, figureHeight: height };
}

export const isoWalkFrames = (facing: IsoFacing) => WALK_COLUMNS.map((column) => `${facing}-${column}`);

export const standingFrame = (facing: IsoFacing) => `${facing}-${STANDING_COLUMN}`;

export const walkTimeScale = (speed: number) => speed / WALKING_SPEED;
