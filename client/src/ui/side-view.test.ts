import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import type { Position } from '../net';
import { sideView, tilesApart } from './side-view';
import { loadStreets } from './street.fixture';

const at = (map: string, x: number, y: number): Position => ({ x, y, map });

describe('with the street maps loaded', () => {
  let unload: () => void;
  beforeEach(() => (unload = loadStreets()));
  afterEach(() => unload());

  it('tells a side-view map by its view property', () => {
    expect(sideView('high_street')).toBe(true);
    expect(sideView('coffee_shop_floor_1')).toBe(true);
    expect(sideView('village')).toBe(false);
    expect(sideView('nowhere')).toBe(false);
  });

  it('measures along the street, however high or low each of them is', () => {
    const lookout = at('lychee_lane', 48, 12);
    expect(tilesApart(at('lychee_lane', 43, 15), lookout)).toBe(5);
    expect(tilesApart(lookout, at('lychee_lane', 43, 15))).toBe(5);
    expect(tilesApart(at('banyan_row', 53, 15), at('banyan_row', 58, 18))).toBe(5);
  });

  it('measures nothing between floors, streets or a street and a floor', () => {
    expect(tilesApart(at('coffee_shop_floor_0', 5, 2), at('coffee_shop_floor_1', 5, 2))).toBeUndefined();
    expect(tilesApart(at('high_street', 50, 15), at('lychee_lane', 17, 15))).toBeUndefined();
    expect(tilesApart(at('high_street', 30, 15), at('coffee_shop_floor_0', 5, 2))).toBeUndefined();
  });

  it('still measures straight on today’s maps', () => {
    expect(tilesApart({ x: 10, y: 10 }, { x: 13, y: 14 })).toBe(5);
    expect(tilesApart(at('coffee_shop', 1, 1), at('coffee_shop', 4, 5))).toBe(5);
  });
});

it('measures straight until a side-view map is loaded, so today’s game is unchanged', () => {
  expect(sideView('lychee_lane')).toBe(false);
  expect(tilesApart(at('lychee_lane', 43, 15), at('lychee_lane', 47, 12))).toBe(5);
});
