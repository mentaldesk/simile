import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { server, type Wall } from '../net';
import { setMuralView } from '../world/murals';
import { village } from './content';
import { eachOnce, readControls, RunToggle, type Held } from './input';
import { RUN_BLEND_SECONDS, RUN_PACE, SidePlayer, type Controls, type MapPosition } from './player';

/** content/street/banyan_row.tmj's wall on house 10, along cells 19 to 21. */
const HOUSE_10: Wall = {
  id: 'banyan_row',
  map: 'banyan_row',
  x: 19,
  y: 15,
  width: 3,
  face: 'south',
  bottom: 0.15,
  top: 1.85,
  mural: {
    work_id: 'kofi-1',
    title: 'Open Door',
    artist: { id: 'kofi', name: 'Kofi Mensah' },
    statement: 'About it.',
    image: '/api/works/kofi-1.png',
  },
};
const DOORSTEP: MapPosition = { x: 17, y: 15, map: 'banyan_row' };
const PASSAGE: MapPosition = { x: 24, y: 15, map: 'banyan_row' };
const NONE: Held = { up: false, down: false, left: false, right: false, run: false };

/** One frame of the side scene's input: the keys held and whether E was pressed. */
function frame(at: MapPosition, held: Partial<Held>, pressedE: boolean) {
  const player = new SidePlayer(village, at);
  const controls: Controls = { x: 0, y: 0, use: false, eTaken: false, run: false };
  readControls({ ...NONE, ...held }, pressedE, player.mapPosition, controls);
  return { controls, door: player.update(controls, 1 / 60) };
}

let unset = () => {};

beforeEach(() => {
  server.dispatch(JSON.stringify({ type: 'murals', walls: [HOUSE_10] }));
  unset = setMuralView({ wallAt: () => undefined });
});

afterEach(() => {
  unset();
  server.dispatch(JSON.stringify({ type: 'murals', walls: [] }));
});

describe('readControls', () => {
  it('reads the arrows as directions, y negative up, running as switched on, and Space', () => {
    const controls: Controls = { x: 0, y: 0, use: false, eTaken: false, run: false };
    const held = { up: true, down: false, left: true, right: false, run: true, jump: true, hold: true };
    readControls(held, false, { x: 30, y: 15, map: 'high_street' }, controls);
    expect(controls).toEqual({ x: -1, y: -1, use: false, eTaken: false, run: true, jump: true, hold: true });
  });

  it('takes house 10’s door with E though its mural is beside it, and not with up', () => {
    const { controls, door } = frame(DOORSTEP, {}, true);

    expect(controls).toMatchObject({ use: true, eTaken: false });
    expect(door?.id).toBe('house_10');
    expect(frame(DOORSTEP, { up: true }, false).door).toBeUndefined();
  });

  it('takes the passage to the High Street with E beside the mural too', () => {
    expect(frame(PASSAGE, {}, true).door?.to.map).toBe('high_street');
  });
});

describe('Shift', () => {
  const tap = (toggle: RunToggle, ...keys: string[]) => {
    for (const key of keys) toggle.keyDown(key);
    for (const key of [...keys].reverse()) toggle.keyUp(key);
  };

  it('switches between walking and running with each press', () => {
    const running = new RunToggle();
    expect(running.on).toBe(false);
    tap(running, 'Shift');
    expect(running.on).toBe(true);
    running.keyDown('Shift');
    running.keyDown('Shift', true);
    running.keyDown('Shift', true);
    running.keyUp('Shift');
    expect(running.on).toBe(false);
    tap(running, 'Shift');
    expect(running.on).toBe(true);
  });

  it('switches once for a tap and an arrow in one frame, though Phaser hands the tap over again with the arrow', () => {
    const running = new RunToggle();
    const down = eachOnce((event: { key: string }) => running.keyDown(event.key));
    const up = eachOnce((event: { key: string }) => running.keyUp(event.key));
    const frame = [
      { type: 'down', key: 'Shift' },
      { type: 'up', key: 'Shift' },
      { type: 'down', key: 'ArrowRight' },
    ];
    for (let i = 1; i <= frame.length; i++) {
      for (const event of frame.slice(0, i)) (event.type === 'down' ? down : up)(event);
    }
    expect(running.on).toBe(true);
  });

  it("isn't switched by Shift+Tab or ?, or by any other key", () => {
    const running = new RunToggle();
    tap(running, 'Shift', 'Tab');
    tap(running, 'Shift', '?');
    tap(running, 'ArrowRight');
    tap(running, ' ');
    expect(running.on).toBe(false);
  });

  it('keeps running through stopping and stairs until Shift is pressed again', () => {
    const running = new RunToggle();
    tap(running, 'Shift');
    const player = new SidePlayer(village, { x: 9, y: 2, map: 'coffee_shop_floor_0' });
    const go = (controls: Partial<Controls>, seconds: number) => {
      for (let t = 0; t < seconds - 1e-9; t += 1 / 60) {
        player.update({ x: 0, y: 0, use: false, eTaken: false, run: running.on, ...controls }, 1 / 60);
      }
    };
    go({ x: 1 }, 1);
    expect(player.drawn.run).toBe(1);
    go({}, 1);
    go({ x: -1 }, RUN_BLEND_SECONDS / 4);
    expect(player.drawn.run).toBe(1);
    player.place({ x: 14, y: 2, map: 'coffee_shop_floor_0' });
    go({}, 1 / 60);
    go({ y: -1 }, 4);
    expect(player.map).toBe('coffee_shop_floor_1');
    const from = player.position.x;
    go({ x: -1 }, 0.5);
    expect(from - player.position.x).toBeCloseTo(0.5 * RUN_PACE * 2.6, 1);
    tap(running, 'Shift');
    go({ x: -1 }, RUN_BLEND_SECONDS + 1 / 60);
    expect(player.drawn.run).toBe(0);
  });
});
