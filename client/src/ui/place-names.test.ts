import { describe, expect, it } from 'vitest';
import type { TiledMap } from '../world/map';
import { placeName } from './place-label';
import { streets } from './street.fixture';

const levels = Object.values(
  import.meta.glob<string>('../../../content/street/levels/*/sewers.tmj', { eager: true, query: '?raw', import: 'default' }),
).map((json) => JSON.parse(json) as TiledMap);
const maps: Record<string, TiledMap> = { ...streets, sewers: levels[0] };

describe('placeName', () => {
  it.each([
    ['a shop', 'noodle_bar_floor_0', 'Golden Bowl Noodles'],
    ['a house', 'house_1_floor_0', '1 Lychee Lane'],
    ['a street', 'banyan_row', 'Banyan Row'],
    ['the metro', 'metro', 'The Old Metro'],
    ['the clinic', 'clinic_floor_0', 'The Clinic'],
    ['a sewers level', 'sewers', 'The Sewers'],
  ])('names %s', (_, mapId, name) => {
    expect(placeName(maps, mapId)).toBe(name);
  });

  it('names an upper floor by its building', () => {
    expect(placeName(maps, 'coffee_shop_floor_2')).toBe('The Daily Grind');
    expect(placeName(maps, 'house_1_floor_1')).toBe('1 Lychee Lane');
  });

  it('names every street and floor', () => {
    for (const mapId of Object.keys(maps)) expect(placeName(maps, mapId), mapId).toBeTruthy();
  });

  it('names every level of the sewers', () => {
    expect(levels.length).toBeGreaterThan(1);
    for (const sewers of levels) expect(placeName({ ...streets, sewers }, 'sewers')).toBe('The Sewers');
  });

  it('names nothing off the maps', () => {
    expect(placeName(maps, 'nowhere')).toBeUndefined();
  });
});
