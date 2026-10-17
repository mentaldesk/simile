import { SPRITE_HEIGHT, WALKING_SPEED } from '../tuning';
import type { Point } from '../view';
import type { SpriteFrame } from './screen';

/** A1's facings on screen (`content/art/README.md`): top-down's four and the three-quarter views. */
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

/** A1's frame in texture px, with the feet on its bottom row. */
export const PIXEL_TEXTURE = { width: 16, height: SPRITE_HEIGHT };

/** Scene px per texture px: a 24 px figure 96 px tall, 1.8 m by the scenery's scale. */
export const PIXEL_SCALE = 4;

const WALK_COLUMNS = [0, 1, 2, 1];
const STANDING_COLUMN = 1;

export function facingFor(step: Point, previous: IsoFacing): IsoFacing {
  if (step.x === 0 && step.y === 0) return previous;
  const eighths = Math.round(Math.atan2(step.y, step.x) / (Math.PI / 4));
  return ISO_FACINGS[(eighths + 8) % 8];
}

/** The frame in scene px: whole scene px per texture px, so every texture px stays square. */
export function pixelFrame(scale: number = PIXEL_SCALE, texture = PIXEL_TEXTURE): SpriteFrame {
  if (!Number.isInteger(scale) || scale < 1) throw new RangeError(`scale ${scale} isn't a whole number`);
  const [width, height] = [texture.width * scale, texture.height * scale];
  return { width, height, anchor: { x: width / 2, y: height }, figureHeight: height };
}

export const isoWalkFrames = (facing: IsoFacing) => WALK_COLUMNS.map((column) => `${facing}-${column}`);

export const standingFrame = (facing: IsoFacing) => `${facing}-${STANDING_COLUMN}`;

/** The walk is `WALK_FPS` at `WALKING_SPEED`, as in top-down, so its pace follows the speed. */
export const walkTimeScale = (speed: number) => speed / WALKING_SPEED;
