import type { Position } from '../net';
import { usedByE } from '../world/reach';
import type { Controls } from './player';

/** Which arrow (or WASD) keys are down, whether running is on, and Space pressed (`jump`) or down (`hold`). */
export type Held = {
  up: boolean;
  down: boolean;
  left: boolean;
  right: boolean;
  run: boolean;
  jump?: boolean;
  hold?: boolean;
};

/** Shift pressed and let go on its own switches running, so Shift+Tab and ? don't. */
export class RunToggle {
  on = false;
  private alone = false;

  keyDown(key: string, repeat = false): void {
    if (key !== 'Shift') this.alone = false;
    else if (!repeat) this.alone = true;
  }

  keyUp(key: string): void {
    if (key !== 'Shift' || !this.alone) return;
    this.alone = false;
    this.on = !this.on;
  }
}

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
  out.jump = !!held.jump;
  out.hold = !!held.hold;
  return out;
}
