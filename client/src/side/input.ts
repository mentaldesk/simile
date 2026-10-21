import type { Position } from '../net';
import { usedByE } from '../world/reach';
import type { Controls } from './player';

/** Which arrow (or WASD) keys are down, and whether Shift is. */
export type Held = { up: boolean; down: boolean; left: boolean; right: boolean; run: boolean };

/** A frame's controls. E uses what's in reach before a door. */
export function readControls(
  held: Held,
  pressedE: boolean,
  at: Position,
  out: Controls,
  reach: (at: Position) => unknown = usedByE,
): Controls {
  out.x = Number(held.right) - Number(held.left);
  out.y = Number(held.down) - Number(held.up);
  out.eTaken = !!reach(at);
  out.use = pressedE && !out.eTaken;
  out.run = held.run;
  return out;
}
