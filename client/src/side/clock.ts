import { server } from '../net';

export const DEFAULT_HOUR = 14;

export function hourOf(time: string): number | undefined {
  const match = /T(\d{2}):(\d{2})(?::(\d{2}(?:\.\d+)?))?/.exec(time);
  if (!match) return undefined;
  return Number(match[1]) + Number(match[2]) / 60 + Number(match[3] ?? 0) / 3600;
}

export class SideClock {
  speed = 1;
  private reading?: { hour: number; at: number };
  private readonly now: () => number;

  constructor(now: () => number = () => performance.now()) {
    this.now = now;
  }

  set(time: string, speed = this.speed): void {
    const hour = hourOf(time);
    this.speed = speed;
    if (hour !== undefined) this.reading = { hour, at: this.now() };
  }

  hour(): number {
    if (!this.reading) return DEFAULT_HOUR;
    const { hour, at } = this.reading;
    const now = hour + (this.speed * (this.now() - at)) / 3_600_000;
    return ((now % 24) + 24) % 24;
  }
}

export const sideClock = new SideClock();
server.on('snapshot', ({ time }) => sideClock.set(time));
server.on('clock', ({ time, speed }) => sideClock.set(time, speed));
