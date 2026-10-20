import type { MapPosition } from './map';
import { SEND_INTERVAL_SECONDS } from './tuning';

const round = (value: number) => Math.round(value * 100) / 100;

export class MoveThrottle {
  private readonly interval: number;
  private sent?: MapPosition;
  private sentAt = -Infinity;

  constructor(interval = SEND_INTERVAL_SECONDS) {
    this.interval = interval;
  }

  /** A move onto another map goes at once. */
  next(position: MapPosition, now: number): MapPosition | undefined {
    const rounded = { x: round(position.x), y: round(position.y), map: position.map };
    const { sent } = this;
    const sameMap = sent?.map === rounded.map;
    if (sameMap && sent.x === rounded.x && sent.y === rounded.y) return undefined;
    if (sameMap && now - this.sentAt < this.interval) return undefined;
    this.sent = rounded;
    this.sentAt = now;
    return rounded;
  }

  forget(): void {
    this.sent = undefined;
    this.sentAt = -Infinity;
  }
}
