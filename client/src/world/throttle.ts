import type { Position } from '../net';
import { SEND_INTERVAL_SECONDS } from './tuning';

const round = (value: number) => Math.round(value * 100) / 100;

export class MoveThrottle {
  private readonly interval: number;
  private sent?: Position;
  private sentAt = -Infinity;

  constructor(interval = SEND_INTERVAL_SECONDS) {
    this.interval = interval;
  }

  next(position: Position, now: number): Position | undefined {
    const rounded = { x: round(position.x), y: round(position.y) };
    if (this.sent?.x === rounded.x && this.sent.y === rounded.y) return undefined;
    if (now - this.sentAt < this.interval) return undefined;
    this.sent = rounded;
    this.sentAt = now;
    return rounded;
  }

  forget(): void {
    this.sent = undefined;
    this.sentAt = -Infinity;
  }
}
