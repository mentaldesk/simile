import { MoveThrottle } from '../world/throttle';
import type { MapPosition } from './player';

const same = (a: MapPosition, b: MapPosition) => a.x === b.x && a.y === b.y && a.map === b.map;

/** The player's positions to send, throttled, and none from a collapse until the scene has woken them. */
export class MoveReport {
  private readonly throttle = new MoveThrottle();
  private readonly sent: MapPosition = { x: NaN, y: NaN, map: '' };
  private waking = false;

  next(position: MapPosition, now: number): MapPosition | undefined {
    if (this.waking) return undefined;
    if (same(position, this.sent)) return undefined;
    const throttled = this.throttle.next(position, now);
    if (!throttled) return undefined;
    Object.assign(this.sent, position);
    return throttled;
  }

  /** The next position goes at once. */
  forget(): void {
    this.throttle.forget();
  }

  /** After a snapshot, a restarted server hears where they are. */
  reset(): void {
    this.throttle.forget();
    this.sent.map = '';
    this.waking = false;
  }

  collapsed(): void {
    this.waking = true;
  }

  /** The scene has placed them where the server woke them. */
  woke(): void {
    this.waking = false;
  }
}
