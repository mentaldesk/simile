import { server, type Creature, type CreatureState, type SideFacing } from '../../net';
import { TILE_M } from '../layout';

/** The server's `SEND`: sim seconds between a moving creature's `creature_moved`s. */
export const SEND_SECONDS = 0.2;
const TWEEN_SECONDS = { min: 0.05, max: 0.5 };
/** Well over a 13 tiles a second dog, or an 8 tiles a second fall, between sends: further snaps. */
export const SNAP_TILES = 4;
/** How long one that's gone takes to keel over and fade. */
export const DOWN_SECONDS = 0.6;

type Point = { x: number; y: number };

/** A creature as the client draws it, between the server's positions. */
export class Tracked {
  creature: Creature;
  /** In its map's cells, as drawn. */
  readonly at: Point;
  private readonly from: Point;
  private readonly to: Point;
  private elapsed = 0;
  private duration = 0;
  private sinceLast = Infinity;
  /** Seconds in its state. */
  seconds = 0;
  /** Metres walked, which steps its cycle. */
  travelled = 0;
  /** Seconds since it went, while it keels over. */
  down?: number;

  constructor(creature: Creature) {
    this.creature = creature;
    const { x, y } = creature.position;
    this.at = { x, y };
    this.from = { x, y };
    this.to = { x, y };
  }

  get map(): string {
    return this.creature.position.map ?? '';
  }

  get state(): CreatureState {
    return this.creature.state;
  }

  get facing(): SideFacing {
    return this.creature.facing;
  }

  /** Tweens over the time since the last one, as often as the server sends them. */
  move(creature: Creature): void {
    const before = this.creature;
    this.creature = creature;
    if (creature.state !== before.state) this.seconds = 0;
    const { x, y } = creature.position;
    const jump = Math.hypot(x - this.at.x, y - this.at.y) > SNAP_TILES;
    if (jump || creature.position.map !== before.position.map) {
      this.place(x, y);
    } else {
      this.from.x = this.at.x;
      this.from.y = this.at.y;
      this.to.x = x;
      this.to.y = y;
      this.elapsed = 0;
      const since = this.sinceLast > TWEEN_SECONDS.max ? SEND_SECONDS : this.sinceLast;
      this.duration = Math.min(Math.max(since, TWEEN_SECONDS.min), TWEEN_SECONDS.max);
    }
    this.sinceLast = 0;
  }

  update(dt: number): void {
    this.sinceLast += dt;
    this.seconds += dt;
    if (this.down !== undefined) this.down += dt;
    if (this.elapsed >= this.duration) return;
    this.elapsed = Math.min(this.elapsed + dt, this.duration);
    const t = this.elapsed / this.duration;
    const x = this.from.x + (this.to.x - this.from.x) * t;
    const y = this.from.y + (this.to.y - this.from.y) * t;
    this.travelled += Math.hypot(x - this.at.x, y - this.at.y) * TILE_M;
    this.at.x = x;
    this.at.y = y;
  }

  private place(x: number, y: number): void {
    this.at.x = this.from.x = this.to.x = x;
    this.at.y = this.from.y = this.to.y = y;
    this.elapsed = this.duration = 0;
  }
}

/** Every creature from `snapshot`, `creature_moved` and `creature_gone`. */
export class Creatures {
  readonly all = new Map<string, Tracked>();

  reset(creatures: readonly Creature[] = []): void {
    const ids = new Set(creatures.map(({ id }) => id));
    for (const id of this.all.keys()) if (!ids.has(id)) this.all.delete(id);
    for (const creature of creatures) this.move(creature);
  }

  move(creature: Creature): void {
    const known = this.all.get(creature.id);
    if (known && known.down === undefined) known.move(creature);
    else this.all.set(creature.id, new Tracked(creature));
  }

  gone(id: string): void {
    const known = this.all.get(id);
    if (known && known.down === undefined) known.down = 0;
  }

  update(dt: number): void {
    for (const [id, tracked] of this.all) {
      tracked.update(dt);
      if (tracked.down !== undefined && tracked.down >= DOWN_SECONDS) this.all.delete(id);
    }
  }
}

export const sideCreatures = new Creatures();
server.on('snapshot', ({ creatures }) => sideCreatures.reset(creatures));
server.on('creature_moved', ({ creature }) => sideCreatures.move(creature));
server.on('creature_gone', ({ creature_id }) => sideCreatures.gone(creature_id));
