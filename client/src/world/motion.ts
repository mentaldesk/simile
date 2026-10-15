import type { Position } from '../net';
import {
  CATCH_UP_TILES,
  IDLE_AFTER_SECONDS,
  MAX_BEHIND_TILES,
  TELEPORT_TILES,
  WALKING_SPEED,
} from './tuning';

export type Facing = 'down' | 'left' | 'right' | 'up';
export const FACINGS: readonly Facing[] = ['down', 'left', 'right', 'up'];

export interface Body {
  readonly position: Position;
  readonly facing: Facing;
  readonly walking: boolean;
}

const DIAGONAL = 0.5;

/** The 4-way facing for a direction of travel. Near diagonals it keeps the previous facing if it can. */
export function facingFor(dx: number, dy: number, previous: Facing): Facing {
  const horizontal: Facing = dx < 0 ? 'left' : 'right';
  const vertical: Facing = dy < 0 ? 'up' : 'down';
  const [ax, ay] = [Math.abs(dx), Math.abs(dy)];
  if (ax === 0 && ay === 0) return previous;
  if (Math.min(ax, ay) < DIAGONAL * Math.max(ax, ay)) return ax > ay ? horizontal : vertical;
  return previous === vertical ? vertical : horizontal;
}

const distance = (a: Position, b: Position) => Math.hypot(b.x - a.x, b.y - a.y);

/** An entity the server moves: it walks through each position the server sends, in order. */
export class Mover implements Body {
  position: Position;
  facing: Facing;
  private readonly waypoints: Position[] = [];
  private still = Infinity;

  constructor(position: Position, facing: Facing = 'down') {
    this.position = { ...position };
    this.facing = facing;
  }

  get walking(): boolean {
    return this.still < IDLE_AFTER_SECONDS;
  }

  moveTo(target: Position): void {
    const gap = distance(this.waypoints.at(-1) ?? this.position, target);
    if (gap > TELEPORT_TILES) this.place(target);
    else if (gap > 0) this.waypoints.push({ ...target });
  }

  place(position: Position): void {
    this.position = { ...position };
    this.waypoints.length = 0;
  }

  update(dt: number): void {
    const behind = this.behind();
    if (behind > MAX_BEHIND_TILES) this.place(this.waypoints.at(-1)!);
    const moving = this.waypoints.length > 0;
    let step = WALKING_SPEED * Math.max(1, behind / CATCH_UP_TILES) * dt;
    while (step > 0 && this.waypoints.length > 0) {
      const next = this.waypoints[0];
      const [dx, dy] = [next.x - this.position.x, next.y - this.position.y];
      const gap = Math.hypot(dx, dy);
      this.facing = facingFor(dx, dy, this.facing);
      if (gap <= step) {
        this.position = { ...next };
        this.waypoints.shift();
        step -= gap;
      } else {
        this.position = { x: this.position.x + (dx / gap) * step, y: this.position.y + (dy / gap) * step };
        step = 0;
      }
    }
    this.still = moving ? 0 : this.still + dt;
  }

  private behind(): number {
    let total = 0;
    let from = this.position;
    for (const waypoint of this.waypoints) {
      total += distance(from, waypoint);
      from = waypoint;
    }
    return total;
  }
}
