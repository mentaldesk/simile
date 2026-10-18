import type { Point } from '../view';
import { IDLE, type IdleTuning } from './tuning';

type Random = () => number;

const between = ([low, high]: readonly [number, number], random: Random) => low + (high - low) * random();

const less = (left: number, dt: number) => (left - dt > 1e-9 ? left - dt : 0);

/**
 * Someone standing or sitting still: now and then they shift their weight, and they turn to whoever
 * near them is talking or, now and then, to whoever is nearest. Tick it while they're still.
 */
export class Idle {
  private shiftIn: number;
  private shiftLeft = 0;
  private glanceIn: number;
  private glanceLeft = 0;
  private glancing?: string;
  private readonly tuning: IdleTuning;
  private readonly random: Random;

  constructor(tuning: IdleTuning = IDLE, random: Random = Math.random) {
    this.tuning = tuning;
    this.random = random;
    this.shiftIn = between(tuning.shiftEvery, random);
    this.glanceIn = between(tuning.glanceEvery, random);
  }

  get shifted(): boolean {
    return this.shiftLeft > 0;
  }

  update(dt: number): void {
    if (this.shiftLeft > 0) this.shiftLeft = less(this.shiftLeft, dt);
    else if ((this.shiftIn -= dt) <= 0) {
      this.shiftLeft = this.tuning.shiftFor;
      this.shiftIn = between(this.tuning.shiftEvery, this.random);
    }
    if (this.glanceLeft > 0) {
      this.glanceLeft = less(this.glanceLeft, dt);
      if (this.glanceLeft === 0) this.glancing = undefined;
    } else if ((this.glanceIn -= dt) <= 0) {
      this.glanceLeft = between(this.tuning.glanceFor, this.random);
      this.glanceIn = between(this.tuning.glanceEvery, this.random);
    }
  }

  /** Back on their feet: the next stop starts afresh. */
  reset(): void {
    this.shiftLeft = 0;
    this.glanceLeft = 0;
    this.glancing = undefined;
  }

  /** The way to turn, as a step on the map, or undefined to face their own way. */
  towards(
    self: string,
    here: Point,
    everyone: ReadonlyMap<string, Point>,
    talking: (id: string) => boolean,
  ): Point | undefined {
    const near = [...everyone]
      .filter(([id]) => id !== self)
      .map(([id, there]) => ({ id, there, gap: Math.hypot(there.x - here.x, there.y - here.y) }))
      .filter(({ gap }) => gap <= this.tuning.turnTiles)
      .sort((a, b) => a.gap - b.gap);
    const target =
      near.find(({ id }) => talking(id)) ??
      (this.glanceLeft > 0 ? (near.find(({ id }) => id === this.glancing) ?? near[0]) : undefined);
    if (this.glanceLeft > 0 && target) this.glancing ??= target.id;
    return target && { x: target.there.x - here.x, y: target.there.y - here.y };
  }
}

/** Who's saying a line now, from `line` messages: until it should have been said. */
export class Talkers {
  private readonly until = new Map<string, number>();

  heard(speaker: string, seconds: number, now = Date.now()): void {
    this.until.set(speaker, now + seconds * 1000);
  }

  talking(id: string, now = Date.now()): boolean {
    return (this.until.get(id) ?? 0) > now;
  }
}
