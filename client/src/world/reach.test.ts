import { afterEach, describe, expect, it } from 'vitest';
import { server, type Wall } from '../net';
import { muralWalls, setMuralView } from './murals';
import { inReach, reachables, usedByE, wayHint, setWayHint, type Reachables } from './reach';
import type { Terminal } from './terminals';

const mural = (id: string, map: string, x: number, width: number): Wall => ({
  id,
  map,
  x,
  y: 15,
  width,
  face: 'south',
  bottom: 1,
  top: 2,
  mural: {
    work_id: `${id}-work`,
    title: id,
    artist: { id: 'kofi', name: 'Kofi Mensah' },
    statement: 'About it.',
    image: `/api/works/${id}.png`,
  },
});
/** content/street/banyan_row.tmj's wall on house 10, along cells 19 to 21. */
const HOUSE_10 = mural('banyan_row', 'banyan_row', 19, 3);
const at = (map: string, x: number, y = 15) => ({ x, y, map });

afterEach(() => server.dispatch(JSON.stringify({ type: 'murals', walls: [] })));

describe('usedByE', () => {
  it('uses the terminal, counter or painting frame the player is at', () => {
    expect(usedByE(at('high_street', 60))).toMatchObject({ kind: 'terminal', terminal: { id: 'terminal_1' } });
    expect(usedByE(at('banyan_row', 60, 18))).toMatchObject({ kind: 'terminal', terminal: { id: 'terminal_3' } });
    expect(usedByE(at('coffee_shop_floor_0', 6, 2))).toMatchObject({
      kind: 'counter',
      interactable: { id: 'coffee_shop_counter' },
    });
    expect(usedByE(at('gallery_floor_1', 14, 2))).toMatchObject({
      kind: 'painting',
      interactable: { id: 'painting_8' },
    });
  });

  it('uses nothing at a machine, at a plain door or nowhere', () => {
    expect(usedByE(at('maker_space_floor_0', 8, 2))).toBeUndefined();
    expect(usedByE(at('high_street', 43))).toBeUndefined();
    expect(usedByE(at('gallery_floor_1', 15, 2))).toBeUndefined();
    expect(usedByE(undefined)).toBeUndefined();
  });

  it('looks at the mural by house 10’s door, rather than going in, once murals are drawn', () => {
    server.dispatch(JSON.stringify({ type: 'murals', walls: [HOUSE_10] }));
    expect(usedByE(at('banyan_row', 17))).toBeUndefined();

    const unset = setMuralView({ wallAt: () => undefined });
    expect(usedByE(at('banyan_row', 17))).toMatchObject({ kind: 'mural', tiles: 1.5, wall: HOUSE_10 });
    expect(usedByE(at('banyan_row', 24))).toMatchObject({ kind: 'mural', wall: HOUSE_10 });
    expect(usedByE(at('banyan_row', 10))).toBeUndefined();
    expect(muralWalls.walls).toEqual([HOUSE_10]);
    unset();
  });
});

describe('inReach', () => {
  const terminal: Terminal = { id: 'terminal_9', label: 'Terminal', map: 'high_street', x: 30, y: 13, width: 1, height: 3 };
  const withWall = (x: number): Reachables => ({
    ...reachables,
    terminals: [terminal],
    walls: () => [mural('wall', 'high_street', x, 2)],
  });

  it('lists everything in reach, nearest first', () => {
    const kinds = (x: number, wall: number) =>
      inReach(at('high_street', x), withWall(wall)).map(({ kind, tiles }) => [kind, tiles]);
    expect(kinds(29, 26)).toEqual([
      ['terminal', 0.5],
      ['mural', 1.5],
    ]);
    expect(kinds(31, 31)).toEqual([
      ['mural', 0],
      ['terminal', 0.5],
    ]);
    expect(kinds(28, 26)).toEqual([['mural', 0.5]]);
  });
});

describe('wayHint', () => {
  it('is the world scene’s, while it says one', () => {
    expect(wayHint()).toBeUndefined();
    const unset = setWayHint(() => 'Press E to take the lift.');
    expect(wayHint()).toBe('Press E to take the lift.');
    unset();
    expect(wayHint()).toBeUndefined();
  });
});
