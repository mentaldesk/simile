import { describe, expect, it } from 'vitest';
import { village } from '../assets';
import { groundHeights, type TiledMapWithTiles } from './ground';

const HEIGHTS = { grass: 0.18, water: -0.35, road: -0.08, crosswalk: -0.08 };

const named = (...names: string[]) => [
  {
    firstgid: 1,
    tiles: names.map((value, id) => ({ id, properties: [{ name: 'name', type: 'string', value }] })),
  },
];

// 1 grass, 2 grass_tufts, 3 road_h, 4 pavement, 5 crosswalk_v
const MAP: TiledMapWithTiles = {
  width: 3,
  height: 2,
  tilewidth: 16,
  tileheight: 16,
  layers: [{ name: 'ground', type: 'tilelayer', data: [1, 2, 3, 4, 5, 0] }],
  tilesets: named('grass', 'grass_tufts', 'road_h', 'pavement', 'crosswalk_v'),
};

describe('groundHeights', () => {
  const heightAt = groundHeights(MAP, HEIGHTS);

  it('raises grass beds and sinks roads, by the first key a tile name starts with', () => {
    expect(heightAt({ x: 0, y: 0 })).toBe(0.18);
    expect(heightAt({ x: 1, y: 0 })).toBe(0.18);
    expect(heightAt({ x: 2, y: 0 })).toBe(-0.08);
    expect(heightAt({ x: 1, y: 1 })).toBe(-0.08);
  });

  it('leaves other tiles, empty cells and anywhere off the map at 0', () => {
    expect(heightAt({ x: 0, y: 1 })).toBe(0);
    expect(heightAt({ x: 2, y: 1 })).toBe(0);
    expect(heightAt({ x: -1, y: 0 })).toBe(0);
    expect(heightAt({ x: 3, y: 0 })).toBe(0);
  });

  it('reads the tile W2 puts an entity on, floor(p + 0.5)', () => {
    expect(heightAt({ x: 1.4, y: 0.4 })).toBe(0.18);
    expect(heightAt({ x: 1.6, y: 0.4 })).toBe(-0.08);
    expect(heightAt({ x: 0.4, y: 0.6 })).toBe(0);
  });

  it('reads the village: road along the north edge, pavement at the square', () => {
    const villageHeights = groundHeights(village as TiledMapWithTiles, HEIGHTS);
    expect(villageHeights({ x: 0, y: 0 })).toBe(-0.08);
    expect(villageHeights({ x: 31, y: 22 })).toBe(0);
  });
});
