import type { Facing, Pose, Position } from '../net';
import type { DollPose } from '../dolls/rig';
import { CATCH_UP_TILES, IDLE_AFTER_SECONDS, MAX_BEHIND_TILES, TELEPORT_TILES } from '../world/tuning';
import { TILE_M } from './layout';
import { climbAt, type ClimbKind, type SideMap } from './maps';

/** Two strides of a 2.04 m doll. */
export const WALK_CYCLE_M = 1.6;
/** Two strides of the same doll running. */
export const RUN_CYCLE_M = 2.4;
/** Two treads, or two rungs. */
export const CLIMB_CYCLE_M: Record<ClimbKind, number> = { stairs: 0.78, ladder: 0.6 };
export const IDLE_CYCLE_SECONDS = 3.2;

/** Tiles a second. */
export const CLIMB_SPEED: Record<ClimbKind, number> = { stairs: 1.3, ladder: 1.0 };
export const RIDE_SPEED = 2.4;

/** Past this the walker is placed: nothing walks it while the scene isn't drawn. */
const MAX_WAYPOINTS = 16;

const SEATED_SPOTS = new Set(['desk', 'seat']);

export type Drawn = {
  pose: DollPose;
  facing: Facing;
  phase: number;
  on?: ClimbKind;
  seated: boolean;
  /** How far a walk has turned into a run, 0 to 1. */
  run: number;
};

export const sideways = (heading: number): Facing => (heading < 0 ? 'west' : 'east');

export function seatedAt(map: SideMap | undefined, x: number, y: number): boolean {
  for (const spot of map?.spots ?? NO_SPOTS) {
    if (spot.x === x && spot.y === y && SEATED_SPOTS.has(spot.type)) return true;
  }
  return false;
}

const NO_SPOTS: SideMap['spots'] = [];

/** Mid-step between rows, either cell's. */
export function climbingAt(map: SideMap, x: number, y: number): ClimbKind | undefined {
  const cx = Math.floor(x + 0.5);
  const cy = Math.floor(y + 0.5);
  if (Math.abs(y - Math.round(y)) < 1e-3) return climbAt(map, cx, cy);
  const [x0, y0] = [Math.floor(x), Math.floor(y)];
  return climbAt(map, x0, y0) ?? climbAt(map, x0 + 1, y0 + 1) ?? climbAt(map, x0, y0 + 1) ?? climbAt(map, x0 + 1, y0);
}

export function drawnOnMap(
  out: Drawn,
  map: SideMap | undefined,
  position: Position,
  { pose, facing }: { pose: Pose; facing: Facing },
  { moving, heading, travelled }: { moving: boolean; heading: number; travelled: number },
  idle: number,
): Drawn {
  const x = Math.floor(position.x + 0.5);
  const y = Math.floor(position.y + 0.5);
  const on = map && climbingAt(map, position.x, position.y);
  out.on = on;
  out.seated = false;
  if (on) {
    out.pose = 'climbing';
    out.facing = on === 'ladder' ? 'north' : sideways(heading);
    out.phase = (travelled * TILE_M) / CLIMB_CYCLE_M[on];
  } else if (moving) {
    out.pose = 'walking';
    out.facing = sideways(heading);
    out.phase = (travelled * TILE_M) / WALK_CYCLE_M;
  } else {
    out.pose = pose === 'walking' || pose === 'climbing' ? 'standing' : pose;
    out.facing = facing;
    out.seated = seatedAt(map, x, y);
    out.phase = idle / IDLE_CYCLE_SECONDS;
  }
  return out;
}

export function drawnCrossing(out: Drawn, kind: ClimbKind | 'lift', heading: number, travelled: number): Drawn {
  out.seated = false;
  if (kind === 'lift') {
    out.pose = 'riding';
    out.facing = 'south';
    out.on = undefined;
    out.phase = 0;
    return out;
  }
  out.pose = 'climbing';
  out.on = kind;
  out.facing = kind === 'ladder' ? 'north' : sideways(heading);
  out.phase = (travelled * TILE_M) / CLIMB_CYCLE_M[kind];
  return out;
}

export const emptyDrawn = (): Drawn => ({ pose: 'standing', facing: 'south', phase: 0, seated: false, run: 0 });

export class Walker {
  readonly position: { x: number; y: number };
  private readonly waypoints: { x: number; y: number }[] = [];
  travelled = 0;
  heading = 1;
  private still = Infinity;
  private readonly speed: number;

  constructor(position: Position, speed: number) {
    this.position = { x: position.x, y: position.y };
    this.speed = speed;
  }

  get moving(): boolean {
    return this.still < IDLE_AFTER_SECONDS;
  }

  get arrived(): boolean {
    return this.waypoints.length === 0;
  }

  moveTo({ x, y }: Position): void {
    const last = this.waypoints.at(-1) ?? this.position;
    const gap = Math.hypot(x - last.x, y - last.y);
    if (gap > TELEPORT_TILES || this.waypoints.length >= MAX_WAYPOINTS) this.place({ x, y });
    else if (gap > 0) this.waypoints.push({ x, y });
  }

  place({ x, y }: Position): void {
    this.position.x = x;
    this.position.y = y;
    this.waypoints.length = 0;
  }

  update(dt: number): void {
    const behind = this.behind();
    if (behind > MAX_BEHIND_TILES) this.place(this.waypoints.at(-1)!);
    const moving = this.waypoints.length > 0;
    let step = this.speed * Math.max(1, behind / CATCH_UP_TILES) * dt;
    while (step > 0 && this.waypoints.length > 0) {
      const next = this.waypoints[0];
      const dx = next.x - this.position.x;
      const dy = next.y - this.position.y;
      const gap = Math.hypot(dx, dy);
      if (dx !== 0) this.heading = Math.sign(dx);
      const covered = Math.min(gap, step);
      if (gap > 0) {
        this.position.x += (dx / gap) * covered;
        this.position.y += (dy / gap) * covered;
      }
      this.travelled += covered;
      step -= covered;
      if (covered >= gap) this.waypoints.shift();
    }
    this.still = moving ? 0 : this.still + dt;
  }

  private behind(): number {
    let total = 0;
    let from = this.position;
    for (const waypoint of this.waypoints) {
      total += Math.hypot(waypoint.x - from.x, waypoint.y - from.y);
      from = waypoint;
    }
    return total;
  }
}
