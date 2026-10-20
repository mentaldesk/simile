import { describe, expect, it, vi } from 'vitest';
import { server, type Wall } from '../net';
import { MURAL_REACH_TILES, muralView, MuralWalls, setMuralView, wallNear } from './murals';

/** content/street/high_street.tmj's walls: the Daily Grind's along cells 27 to 29. */
const GRIND: Wall = {
  id: 'daily_grind',
  map: 'high_street',
  x: 27,
  y: 15,
  width: 3,
  face: 'south',
  bottom: 1.05,
  top: 1.9,
  mural: {
    work_id: 'mars',
    title: 'Red Horizon',
    artist: { id: 'kofi', name: 'Kofi Mensah' },
    statement: 'Mars is a billionaire’s lifeboat.',
    image: '/api/works/mars.png',
  },
};
const SHOP: Wall = { ...GRIND, id: 'corner_shop', x: 20, width: 4, mural: { ...GRIND.mural!, work_id: 'river' } };
const street = (x: number, y = 15) => ({ x, y, map: 'high_street' });

describe('wallNear', () => {
  it('finds a painted wall within reach along the street of either end', () => {
    expect(wallNear([GRIND], street(28))).toBe(GRIND);
    expect(wallNear([GRIND], street(27 - MURAL_REACH_TILES - 0.5))).toBe(GRIND);
    expect(wallNear([GRIND], street(29 + MURAL_REACH_TILES + 0.5))).toBe(GRIND);
  });

  it('reaches it from any height on the street', () => {
    expect(wallNear([GRIND], street(28, 12))).toBe(GRIND);
  });

  it('finds none out of reach, on a blank wall, or nowhere', () => {
    expect(wallNear([GRIND], street(27 - MURAL_REACH_TILES - 0.6))).toBeUndefined();
    expect(wallNear([GRIND], street(33.6))).toBeUndefined();
    expect(wallNear([{ ...GRIND, mural: null }], street(28))).toBeUndefined();
    expect(wallNear([GRIND], undefined)).toBeUndefined();
  });

  it('finds none on another street, inside, or on a position or wall with no map', () => {
    expect(wallNear([GRIND], { x: 28, y: 15, map: 'lychee_lane' })).toBeUndefined();
    expect(wallNear([GRIND], { x: 3, y: 2, map: 'coffee_shop_floor_0' })).toBeUndefined();
    expect(wallNear([GRIND], { x: 28, y: 15 })).toBeUndefined();
    expect(wallNear([{ ...GRIND, map: undefined }], { x: 28, y: 15 })).toBeUndefined();
  });

  it('finds the nearer of two', () => {
    expect(wallNear([SHOP, GRIND], street(25))).toBe(SHOP);
    expect(wallNear([SHOP, GRIND], street(25.6))).toBe(GRIND);
  });
});

describe('MuralWalls', () => {
  it('keeps the latest walls and tells listeners', () => {
    const walls = new MuralWalls(server);
    const heard = vi.fn();
    const stop = walls.onChange(heard);

    server.dispatch(JSON.stringify({ type: 'murals', walls: [GRIND] }));

    expect(walls.wall('daily_grind')?.mural?.title).toBe('Red Horizon');
    expect(heard).toHaveBeenCalledWith(walls.walls);
    stop();
    server.dispatch(JSON.stringify({ type: 'murals', walls: [] }));
    expect(walls.walls).toEqual([]);
    expect(heard).toHaveBeenCalledTimes(1);
  });
});

describe('muralView', () => {
  it('is the registered view until it unregisters', () => {
    const view = { wallAt: () => 'daily_grind' };
    const unset = setMuralView(view);
    expect(muralView()).toBe(view);
    unset();
    expect(muralView()).toBeUndefined();
  });
});
