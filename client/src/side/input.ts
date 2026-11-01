import type { Controls } from './player';

/** Which arrow (or WASD) keys are down, whether running is on, and a jump key pressed (`jump`) or down (`hold`). */
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

/** Phaser's names for the keys that jump: Space, and PageUp for keyboards that can't hold Space. */
export const JUMP_KEYS = ['SPACE', 'PAGE_UP'] as const;

type JumpPress = Pick<KeyboardEvent, 'key' | 'repeat' | 'preventDefault'>;

/** Either jump key: pressed since the last read, and held while any is down. */
export class JumpKeys {
  private pressed = false;
  private readonly keys: readonly { readonly isDown: boolean }[];

  constructor(keys: readonly { readonly isDown: boolean }[]) {
    this.keys = keys;
  }

  readonly keyDown = (event: JumpPress): void => {
    if (event.key === 'PageUp') event.preventDefault();
    this.pressed ||= !event.repeat;
  };

  read(held: Held): void {
    held.jump = this.pressed;
    held.hold = this.keys.some((key) => key.isDown);
    this.pressed = false;
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
