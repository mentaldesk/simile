// @vitest-environment jsdom
import type Phaser from 'phaser';
import { describe, expect, it, vi } from 'vitest';
import type { Item } from '../net';
import { onPress } from './input';
import { MoveReport } from './report';
import { canFire, firesNext, firing, reloading, ShotView, shotAt, sideOf, weaponLine } from './shooting';

const pistol = (rounds = 6, condition = 1): Item => ({
  id: 'pistol',
  kind: 'weapon',
  name: 'Plastic pistol',
  weight: 0.5,
  charge: null,
  on: null,
  material: 'plastic',
  rounds,
  capacity: 6,
  condition,
});
const stack = (amount: number): Item => ({ id: 'rounds', kind: 'rounds', name: 'Plastic rounds', weight: 0.02, charge: null, on: null, amount, material: 'plastic' });
const lamp: Item = { id: 'lamp', kind: 'lamp', name: 'Lamp', weight: 1, charge: 1, on: false };

describe('firing', () => {
  it('sends a move the throttle is holding back before the shot', () => {
    const moves = new MoveReport();
    expect(moves.next({ x: 10, y: 15, map: 'metro' }, 1)).toBeDefined();
    const position = { x: 10.4, y: 15, map: 'metro' };
    expect(moves.next(position, 1.01), 'held back').toBeUndefined();

    expect(firing(moves, position, 1.02, [lamp, pistol()], 'west')).toEqual([
      { type: 'player_move', position },
      { type: 'fire', facing: 'west' },
    ]);
  });

  it('sends only the shot when the server already has where they are', () => {
    const moves = new MoveReport();
    const position = { x: 10, y: 15, map: 'metro' };
    moves.next(position, 1);

    expect(firing(moves, position, 5, [pistol()], 'east')).toEqual([{ type: 'fire', facing: 'east' }]);
  });

  it('holds its fire with nothing loaded, or only a worn-out weapon', () => {
    const moves = new MoveReport();
    const position = { x: 10, y: 15, map: 'metro' };

    expect(firing(moves, position, 1, undefined, 'east')).toEqual([]);
    expect(firing(moves, position, 1, [lamp], 'east')).toEqual([]);
    expect(firing(moves, position, 1, [pistol(0)], 'east')).toEqual([]);
    expect(firing(moves, position, 1, [pistol(3, 0)], 'east')).toEqual([]);
    expect(firing(moves, position, 1, [pistol(3, 0), pistol(1)], 'east')).toHaveLength(2);
  });
});

describe('canFire', () => {
  const free = { passing: false, climbing: undefined, bed: 0 };

  it('goes when they’re free', () => {
    expect(canFire(free)).toBe(true);
  });

  it('holds its fire through a door, on a ladder, stairs or the lift, and in bed', () => {
    expect(canFire({ ...free, passing: true })).toBe(false);
    for (const climbing of ['ladder', 'stairs', 'lift']) expect(canFire({ ...free, climbing })).toBe(false);
    expect(canFire({ ...free, bed: 0.5 })).toBe(false);
    expect(canFire({ ...free, bed: 1 })).toBe(false);
  });
});

describe('the weapon fire would use', () => {
  it('is the first loaded, else the first to reload, else any', () => {
    const [empty, loaded, worn] = [pistol(0, 0.5), pistol(3, 0.9), pistol(2, 0)];
    expect(firesNext([worn, empty, loaded])).toBe(loaded);
    expect(firesNext([worn, empty])).toBe(empty);
    expect(firesNext([lamp, worn])).toBe(worn);
    expect(firesNext([lamp])).toBeUndefined();
    expect(firesNext(undefined)).toBeUndefined();
  });
});

describe('reloading', () => {
  it('goes only with room in a weapon that still works, and rounds for it', () => {
    expect(reloading([pistol(2), stack(1)])).toEqual({ type: 'reload' });
    expect(reloading(undefined)).toBeUndefined();
    expect(reloading([pistol(), stack(1)])).toBeUndefined();
    expect(reloading([pistol(2)])).toBeUndefined();
    expect(reloading([pistol(2, 0), stack(1)])).toBeUndefined();
    expect(reloading([stack(1)])).toBeUndefined();
  });
});

describe('the weapon’s line', () => {
  it('shows nothing without a weapon', () => {
    expect(weaponLine(undefined)).toBeUndefined();
    expect(weaponLine([lamp, stack(3)])).toBeUndefined();
  });

  it('shows the rounds, the spare and the condition', () => {
    expect(weaponLine([pistol(4, 0.8), stack(3)])).toBe('X  Plastic pistol: 4/6, 3 spare, 80% condition');
  });

  it('says to reload when it’s empty and there are rounds', () => {
    expect(weaponLine([pistol(0, 0.5), stack(3)])).toBe('X  Plastic pistol: 0/6, 3 spare, 50% condition, R reloads');
    expect(weaponLine([pistol(0, 0.5)])).toBe('X  Plastic pistol: 0/6, 0 spare, 50% condition');
  });

  it('says when it’s worn out, and goes by one that still works', () => {
    expect(weaponLine([pistol(2, 0)])).toBe('Plastic pistol: worn out');
    expect(weaponLine([pistol(2, 0), pistol(1, 0.5)])).toContain('1/6');
  });
});

describe('the keys', () => {
  it('takes a fresh press only, not a repeat, Cmd, Ctrl or Alt, or a key for a focused field', () => {
    let pressed = 0;
    const press = onPress(() => pressed++);
    const key = (init: KeyboardEventInit, target: EventTarget = document.body) => {
      const event = new KeyboardEvent('keydown', { key: 'r', bubbles: true, ...init });
      target.addEventListener('keydown', (seen) => press(seen as KeyboardEvent), { once: true });
      target.dispatchEvent(event);
      return event;
    };

    const once = key({});
    expect(pressed).toBe(1);
    press(once);
    expect(pressed, 'Phaser hands a frame’s event over again').toBe(1);
    key({ repeat: true });
    key({ metaKey: true });
    key({ ctrlKey: true });
    key({ altKey: true });
    const field = document.body.appendChild(document.createElement('input'));
    key({}, field);
    expect(pressed).toBe(1);
  });
});

describe('the shot’s view', () => {
  const view = { x: 0, bottom: 100 } as Phaser.Geom.Rectangle;
  const at = { x: 10, y: 15 };

  function shots() {
    const graphics = { setDepth: () => graphics, clear: vi.fn(), fillStyle: () => graphics, fillRect: vi.fn(() => graphics), fillCircle: vi.fn(() => graphics), destroy: vi.fn() };
    const line = { setOrigin: () => line, setDepth: () => line, setVisible: vi.fn(() => line), setText: vi.fn(() => line), setScale: () => line, setPosition: () => line, destroy: vi.fn(), text: '', visible: false };
    const scene = { add: { graphics: () => graphics, text: () => line } } as unknown as Phaser.Scene;
    return { shots: new ShotView(scene), graphics, line };
  }

  it('draws nothing before a shot', () => {
    const { shots: view_, graphics } = shots();
    view_.update(1 / 60, at, 'east', undefined, view, 1);
    expect(graphics.fillRect).not.toHaveBeenCalled();
    expect(graphics.fillCircle).not.toHaveBeenCalled();
  });

  it('draws the pistol and a flash past its muzzle the way they face, then only the pistol, then neither', () => {
    const { shots: view_, graphics } = shots();
    view_.fired();
    view_.update(1 / 60, at, 'east', undefined, view, 1);
    expect(graphics.fillRect).toHaveBeenCalledTimes(1);
    expect(graphics.fillCircle).toHaveBeenCalledTimes(2);
    const [[x]] = graphics.fillCircle.mock.calls as unknown as [[number]];
    expect(x).toBeGreaterThan(shotAt(at, 'east').x);

    view_.update(0.1, at, 'east', undefined, view, 1);
    expect(graphics.fillRect).toHaveBeenCalledTimes(2);
    expect(graphics.fillCircle).toHaveBeenCalledTimes(2);

    view_.update(0.3, at, 'east', undefined, view, 1);
    expect(graphics.fillRect).toHaveBeenCalledTimes(2);
  });

  it('flashes west of them facing west', () => {
    const { shots: view_, graphics } = shots();
    view_.fired();
    view_.update(1 / 60, at, 'west', undefined, view, 1);
    const [[x]] = graphics.fillCircle.mock.calls as unknown as [[number]];
    expect(x).toBeLessThan(shotAt(at, 'west').x);
  });

  it('draws no shot while they aren’t shown', () => {
    const { shots: view_, graphics } = shots();
    view_.fired();
    view_.update(1 / 60, undefined, 'east', undefined, view, 1);
    expect(graphics.fillRect).not.toHaveBeenCalled();
  });

  it('shows the weapon’s line only while there is one', () => {
    const { shots: view_, line } = shots();
    view_.update(1 / 60, at, 'east', 'X  Plastic pistol', view, 1);
    expect(line.setVisible).toHaveBeenLastCalledWith(true);
    expect(line.setText).toHaveBeenCalledWith('X  Plastic pistol');
    view_.update(1 / 60, at, 'east', undefined, view, 1);
    expect(line.setVisible).toHaveBeenLastCalledWith(false);
  });
});

describe('where a shot is drawn', () => {
  it('goes the way they face', () => {
    const at = { x: 10, y: 15 };
    expect(shotAt(at, 'east').x).toBeGreaterThan(shotAt(at, 'west').x);
    expect(sideOf('north', 'west')).toBe('west');
    expect(sideOf('east', 'west')).toBe('east');
  });
});
