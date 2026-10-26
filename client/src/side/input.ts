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

/** `handle`, called once for each event: Phaser hands a frame's earlier key events to its listeners again with each new one. */
export function eachOnce<E extends object>(handle: (event: E) => void): (event: E) => void {
  const seen = new WeakSet<E>();
  return (event) => {
    if (seen.has(event)) return;
    seen.add(event);
    handle(event);
  };
}

export function readControls(held: Held, pressedE: boolean, out: Controls): Controls {
  out.x = Number(held.right) - Number(held.left);
  out.y = Number(held.down) - Number(held.up);
  out.use = pressedE;
  out.run = held.run;
  out.jump = !!held.jump;
  out.hold = !!held.hold;
  return out;
}
