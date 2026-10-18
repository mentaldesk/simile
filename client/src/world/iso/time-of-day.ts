import { server } from '../../net';

/** The lighting sets and their sim hours, as in `server/simile/art/iso/lighting.py`. */
export const LIGHTING_SETS = {
  night: [21, 5],
  morning: [5, 11],
  afternoon: [11, 17],
  evening: [17, 21],
} as const satisfies Record<string, readonly [number, number]>;

export type LightingSet = keyof typeof LIGHTING_SETS;

export const CROSSFADE_MINUTES = 60;

export const DEFAULT_HOUR = 14;

export type Layer = { set: LightingSet; weight: number };

const SETS = Object.keys(LIGHTING_SETS) as LightingSet[];

const modulo = (value: number, by: number) => ((value % by) + by) % by;

const within = (hour: number, [start, end]: readonly [number, number]) =>
  start < end ? hour >= start && hour < end : hour >= start || hour < end;

/** The sets to draw at a sim-clock hour, outgoing first, and their weights: `lighting.blend`. */
export function blend(hour: number): Layer[] {
  const half = CROSSFADE_MINUTES / 120;
  for (const [i, set] of SETS.entries()) {
    const since = modulo(hour - LIGHTING_SETS[set][0] + 12, 24) - 12;
    if (-half < since && since < half) {
      const x = (since + half) / (2 * half);
      const weight = x * x * (3 - 2 * x);
      return [
        { set: SETS.at(i - 1)!, weight: 1 - weight },
        { set, weight },
      ];
    }
  }
  return [{ set: SETS.find((set) => within(modulo(hour, 24), LIGHTING_SETS[set]))!, weight: 1 }];
}

/** The set `blend` fades to next, if its fade starts within `hours` and none is under way. */
export function nextSet(hour: number, hours: number): LightingSet | undefined {
  const now = blend(hour);
  if (now.length > 1) return undefined;
  const next = SETS[(SETS.indexOf(now[0].set) + 1) % SETS.length];
  const half = CROSSFADE_MINUTES / 120;
  return modulo(LIGHTING_SETS[next][0] - half - hour, 24) <= hours ? next : undefined;
}

/** The hour of a sim time, `YYYY-MM-DDTHH:MM[:SS]…`, with minutes and seconds as a fraction. */
export function hourOf(time: string): number | undefined {
  const match = /T(\d{2}):(\d{2})(?::(\d{2}(?:\.\d+)?))?/.exec(time);
  if (!match) return undefined;
  return Number(match[1]) + Number(match[2]) / 60 + Number(match[3] ?? 0) / 3600;
}

export class SimClock {
  speed = 1;
  private reading?: { hour: number; at: number };
  private readonly waiting = new Set<() => void>();
  private readonly now: () => number;

  /** `now` is real time in ms. */
  constructor(now: () => number = () => performance.now()) {
    this.now = now;
  }

  set(time: string, speed = this.speed): void {
    const hour = hourOf(time);
    this.speed = speed;
    if (hour === undefined) return;
    this.reading = { hour, at: this.now() };
    for (const resolve of this.waiting) resolve();
  }

  hour(): number | undefined {
    if (!this.reading) return undefined;
    const { hour, at } = this.reading;
    return modulo(hour + (this.speed * (this.now() - at)) / 3_600_000, 24);
  }

  known(timeoutMs: number): Promise<void> {
    if (this.reading) return Promise.resolve();
    return new Promise((resolve) => {
      const done = () => {
        clearTimeout(timer);
        this.waiting.delete(done);
        resolve();
      };
      const timer = setTimeout(done, timeoutMs);
      this.waiting.add(done);
    });
  }
}

export const simClock = new SimClock();
server.on('snapshot', ({ time }) => simClock.set(time));
server.on('clock', ({ time, speed }) => simClock.set(time, speed));
