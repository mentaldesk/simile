import { server } from '../../net';

/** The lighting sets and their sim hours, as in `server/simile/art/iso/lighting.py`. */
export const LIGHTING_SETS = {
  night: [21, 5],
  morning: [5, 11],
  afternoon: [11, 17],
  evening: [17, 21],
} as const satisfies Record<string, readonly [number, number]>;

export type LightingSet = keyof typeof LIGHTING_SETS;

export const DEFAULT_SET: LightingSet = 'afternoon';

/** The hour of a sim time, `YYYY-MM-DDTHH:MM…`, with minutes as a fraction. */
export function hourOf(time: string): number | undefined {
  const match = /T(\d{2}):(\d{2})/.exec(time);
  return match ? Number(match[1]) + Number(match[2]) / 60 : undefined;
}

const within = (hour: number, [start, end]: readonly [number, number]) =>
  start < end ? hour >= start && hour < end : hour >= start || hour < end;

export function lightingSetAt(time: string | undefined): LightingSet {
  const hour = time === undefined ? undefined : hourOf(time);
  if (hour === undefined) return DEFAULT_SET;
  const sets = Object.keys(LIGHTING_SETS) as LightingSet[];
  return sets.find((set) => within(hour, LIGHTING_SETS[set])) ?? DEFAULT_SET;
}

/** The latest sim time from the server, from the snapshot or a `clock` message. */
export class SimClock {
  time?: string;
  private readonly waiting = new Set<() => void>();

  set(time: string): void {
    this.time = time;
    for (const resolve of this.waiting) resolve();
  }

  known(timeoutMs: number): Promise<string | undefined> {
    if (this.time !== undefined) return Promise.resolve(this.time);
    return new Promise((resolve) => {
      const done = () => {
        clearTimeout(timer);
        this.waiting.delete(done);
        resolve(this.time);
      };
      const timer = setTimeout(done, timeoutMs);
      this.waiting.add(done);
    });
  }
}

export const simClock = new SimClock();
server.on('snapshot', ({ time }) => simClock.set(time));
server.on('clock', ({ time }) => simClock.set(time));
