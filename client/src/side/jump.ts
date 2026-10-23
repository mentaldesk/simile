import table from '../../../content/street/jump.json';
import { fitted } from '../dolls/bionics';
import type { Body } from '../net';
import { climbAt, isSolid, type SideMap } from './maps';

/** The jump the server checks positions by, from server/simile/street/jump.py. */
export const JUMP_TABLE = table;
/** The hydraulic legs' jump, a row higher under the same gravity. */
export const LEGS_TABLE = { ...table, ...table.legs };
export type JumpTable = typeof JUMP_TABLE | typeof LEGS_TABLE;
/** Tiles the feet rise with Space held, in `JUMP_RISE_SECONDS`. */
export const JUMP_RISE = table.rise;
export const JUMP_RISE_SECONDS = table.rise_seconds;
/** Tiles a second a second, rising with Space held. */
export const GRAVITY = (2 * JUMP_RISE) / JUMP_RISE_SECONDS ** 2;
/** The jump the player makes on their own legs, or on the hydraulic legs once fitted. */
export const jumpOf = (body?: Body): JumpTable => (fitted(body).includes('hydraulic_legs') ? LEGS_TABLE : JUMP_TABLE);

/** Tiles a second up at take-off, to rise `rise` tiles with Space held. */
export const jumpSpeed = (rise: number): number => Math.sqrt(2 * GRAVITY * rise);
/** Times `GRAVITY` falling, or once Space is let go, so a jump comes down quicker than it goes up. */
export const FALL_GRAVITY = table.fall_gravity;
/** Of its speed up a jump keeps when Space is let go on the way up. */
export const JUMP_CUT = table.cut;
export const MAX_FALL_SPEED = 18;
/** Tiles a second a second in the air: towards the speed the arrows ask for, or to a stop with neither. */
export const AIR_ACCEL = 30;
export const AIR_BRAKE = 6;
/** After walking off a ledge, Space still jumps for this long. */
export const COYOTE_SECONDS = table.coyote_seconds;
/** Space pressed this long before landing jumps again on landing. */
export const BUFFER_SECONDS = table.buffer_seconds;
export const LANDING_SECONDS = 0.12;
/** Half the width of the feet, which can stand on a ledge's edge, and of the body, which walls stop. */
export const FOOT = table.foot;
/** From the feet to the top of the head. */
export const BODY = table.body;
/** Cells along a row from where a run jump takes off to where it lands, and rows up, for the server's paths. */
export const JUMP_REACH = table.cells;
export const JUMP_UP = table.rows;

/** How a jump or a fall is moving, in tiles a second, y down. `held` while Space is still held from the jump. */
export type Air = { vx: number; vy: number; held: boolean };

const EPSILON = 1e-6;
/** Each step through the air moves less than this, so it can't pass through a cell. */
const STEP_TILES = 0.2;

/** Columns a stretch from `x0` to `x1` covers, positions being the middle of their cell. */
function columns(x0: number, x1: number): [number, number] {
  return [Math.floor(x0 + 0.5 + EPSILON), Math.floor(x1 + 0.5 - EPSILON)];
}

/** Anything solid where the body is, standing at `x` with its feet `feet` rows down. */
function blocked(map: SideMap, x: number, feet: number): boolean {
  const [left, right] = columns(x - FOOT, x + FOOT);
  const [top, bottom] = [Math.floor(feet - BODY + EPSILON), Math.floor(feet - EPSILON)];
  for (let cx = left; cx <= right; cx++) {
    for (let cy = top; cy <= bottom; cy++) if (isSolid(map, cx, cy)) return true;
  }
  return false;
}

/** The cell along row `y` that the feet at `x` stand on: the one under the middle, else under a foot. */
export function footing(map: SideMap, x: number, y: number): number | undefined {
  const middle = Math.floor(x + 0.5);
  if (standsOn(map, middle, y)) return middle;
  const [left, right] = columns(x - FOOT, x + FOOT);
  for (let cx = left; cx <= right; cx++) if (standsOn(map, cx, y)) return cx;
  return undefined;
}

const standsOn = (map: SideMap, x: number, y: number) =>
  Number.isInteger(y) && !isSolid(map, x, y) && isSolid(map, x, y + 1);

/** The row the feet at `at` would land on, falling straight down. */
export function landingRow(map: SideMap, at: { x: number; y: number }): number {
  const x = Math.floor(at.x + 0.5);
  let row = Math.max(Math.ceil(at.y), 0);
  while (row < map.height && !isSolid(map, x, row + 1)) row++;
  return row;
}

/** Past the end of a walk along row `y`, open air with nothing to climb in it or under it. */
export function dropBeyond(map: SideMap, end: number, y: number, way: -1 | 1): boolean {
  const x = end + way;
  if (x < 0 || x >= map.width) return false;
  return !isSolid(map, x, y) && !isSolid(map, x, y + 1) && !climbAt(map, x, y) && !climbAt(map, x, y + 1);
}

/** Moves `at` through the air for `dt`, stopped by anything solid and kept on the map; true once it lands. */
export function fly(map: SideMap, at: { x: number; y: number }, air: Air, dt: number): boolean {
  const steps = Math.max(1, Math.ceil((Math.max(Math.abs(air.vx), Math.abs(air.vy)) * dt) / STEP_TILES));
  const step = dt / steps;
  for (let i = 0; i < steps; i++) {
    const x = Math.min(Math.max(at.x + air.vx * step, 0), map.width - 1);
    if (blocked(map, x, at.y + 1)) {
      const [left, right] = columns(x - FOOT, x + FOOT);
      at.x = air.vx > 0 ? right - 0.5 - FOOT - EPSILON : left + 0.5 + FOOT + EPSILON;
      air.vx = 0;
    } else at.x = x;
    const feet = at.y + 1 + air.vy * step;
    if (blocked(map, at.x, feet)) {
      if (air.vy > 0) {
        at.y = Math.floor(feet - EPSILON) - 1;
        air.vy = 0;
        return true;
      }
      at.y = Math.ceil(feet - BODY) + BODY - 1;
      air.vy = 0;
    } else at.y = feet - 1;
  }
  return false;
}

/** Speeds `air` up or down for `dt`: towards `vx` along, and by gravity, stronger once falling or let go. */
export function steer(air: Air, vx: number, dt: number): void {
  const accel = (vx !== 0 ? AIR_ACCEL : AIR_BRAKE) * dt;
  air.vx = air.vx < vx ? Math.min(air.vx + accel, vx) : Math.max(air.vx - accel, vx);
  const gravity = air.vy < 0 && air.held ? GRAVITY : GRAVITY * FALL_GRAVITY;
  air.vy = Math.min(air.vy + gravity * dt, MAX_FALL_SPEED);
}
