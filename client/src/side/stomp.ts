import type { CreatureKind } from '../net';
import type { Tracked } from './creatures/creatures';

/** Tiles above its floor a rat's back is: the server's `STOMP_TOP`. */
export const STOMP_TOP = 0.4;
/** Tiles either side of a rat the feet land on it: their foot and half a rat. */
export const STOMP_REACH = 0.6;
/** Tiles the feet rise bouncing off one. */
export const BOUNCE_RISE = 1.2;
const STOMPED: ReadonlySet<CreatureKind> = new Set(['rat']);

/** Where the feet stop on the back of a rat they came down onto from `from` to `to` at `x`, or nowhere. */
export function stompedOn(creatures: Iterable<Tracked>, map: string, x: number, from: number, to: number): number | undefined {
  for (const tracked of creatures) {
    if (tracked.down !== undefined || tracked.map !== map || !STOMPED.has(tracked.creature.kind)) continue;
    const top = tracked.at.y - STOMP_TOP;
    if (from <= top && to >= top && Math.abs(x - tracked.at.x) <= STOMP_REACH) return top;
  }
  return undefined;
}
