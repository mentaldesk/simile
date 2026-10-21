import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { server, type Wall } from '../net';
import { setMuralView } from '../world/murals';
import { village } from './content';
import { readControls, type Held } from './input';
import { SidePlayer, type Controls, type MapPosition } from './player';

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
  it('reads the arrows as directions, y negative up, and Shift as running', () => {
    const controls: Controls = { x: 0, y: 0, use: false, eTaken: false, run: false };
    const held = { up: true, down: false, left: true, right: false, run: true };
    readControls(held, false, { x: 30, y: 15, map: 'high_street' }, controls);
    expect(controls).toEqual({ x: -1, y: -1, use: false, eTaken: false, run: true });
  });

  it('leaves E to the mural by house 10’s door, so one press doesn’t also go in', () => {
    const { controls, door } = frame(DOORSTEP, {}, true);

    expect(controls).toMatchObject({ use: false, eTaken: true });
    expect(door).toBeUndefined();
  });

  it('takes house 10’s door with up instead, while the mural has E', () => {
    expect(frame(DOORSTEP, { up: true }, false).door?.id).toBe('house_10');
  });

  it('leaves E to the mural at the passage to the High Street too', () => {
    expect(frame(PASSAGE, {}, true).door).toBeUndefined();
    expect(frame(PASSAGE, { up: true }, false).door?.to.map).toBe('high_street');
  });

  it('takes the door with E once nothing is in reach, and not with up', () => {
    server.dispatch(JSON.stringify({ type: 'murals', walls: [] }));

    const { controls, door } = frame(DOORSTEP, {}, true);

    expect(controls).toMatchObject({ use: true, eTaken: false });
    expect(door?.id).toBe('house_10');
    expect(frame(DOORSTEP, { up: true }, false).door).toBeUndefined();
  });
});
