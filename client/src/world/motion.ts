import type { Position } from '../net';
import {
  CATCH_UP_TILES,
  IDLE_AFTER_SECONDS,
  MAX_BEHIND_TILES,
  TELEPORT_TILES,
  WALKING_SPEED,
} from './tuning';

export interface Body {
  readonly position: Position;
  readonly walking: boolean;
}

const distance = (a: Position, b: Position) => Math.hypot(b.x - a.x, b.y - a.y);

/** An entity the server moves: it walks through each position the server sends, in order. */
export class Mover implements Body {
  position: Position;
  private readonly waypoints: Position[] = [];
  private still = Infinity;

  constructor(position: Position) {
    this.position = { ...position };
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
