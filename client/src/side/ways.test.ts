import { describe, expect, it } from 'vitest';
import { village } from './content';
import { SidePlayer, type MapPosition } from './player';
import { wayHint } from './ways';

const hintAt = (position: MapPosition, eTaken = false) => {
  const way = new SidePlayer(village, position).way();
  return way && wayHint(village, way, eTaken);
};

describe('wayHint', () => {
  it('names the building a front door goes into, and the street out of it', () => {
    expect(hintAt({ x: 43, y: 15, map: 'high_street' })).toBe('Press E or ↑ to go into The Daily Grind.');
    expect(hintAt({ x: 17, y: 15, map: 'banyan_row' })).toBe('Press E or ↑ to go into 3 Banyan Row.');
    expect(hintAt({ x: 18, y: 2, map: 'coffee_shop_floor_0' })).toBe('Press E or ↑ to go out onto High Street.');
  });

  it('names the street a street door goes to', () => {
    expect(hintAt({ x: 46, y: 15, map: 'high_street' })).toBe('Press E or ↑ to go to Kapok Walk.');
    expect(hintAt({ x: 24, y: 15, map: 'banyan_row' })).toBe('Press E or ↑ to go to High Street.');
  });

  it('says which way stairs and ladders between floors go', () => {
    expect(hintAt({ x: 15, y: 2, map: 'coffee_shop_floor_0' })).toBe('Press E to take the stairs up.');
    expect(hintAt({ x: 11, y: 2, map: 'coffee_shop_floor_1' })).toBe('Press E to take the stairs down.');
    expect(hintAt({ x: 6, y: 2, map: 'maker_space_floor_1' })).toBe('Press E to climb up the ladder.');
    expect(hintAt({ x: 6, y: 2, map: 'maker_space_floor_2' })).toBe('Press E to climb down the ladder.');
  });

  it('says which floor each end of a lift goes to', () => {
    expect(hintAt({ x: 16, y: 2, map: 'gallery_floor_0' })).toBe('Press E to take the lift to the first floor.');
    expect(hintAt({ x: 15, y: 2, map: 'gallery_floor_0' })).toBe('Press E to take the lift to the second floor.');
    expect(hintAt({ x: 16, y: 2, map: 'gallery_floor_2' })).toBe('Press E to take the lift to the ground floor.');
  });

  it('takes stairs and ladders on a street from either end', () => {
    expect(hintAt({ x: 53, y: 15, map: 'banyan_row' })).toBe('Press E to take the stairs down.');
    expect(hintAt({ x: 45, y: 15, map: 'lychee_lane' })).toBe('Press E to climb up the ladder.');
    expect(hintAt({ x: 46, y: 12, map: 'lychee_lane' })).toBe('Press E to climb down the ladder.');
  });

  it('still says up takes a door while E is used for something in reach', () => {
    expect(hintAt({ x: 17, y: 15, map: 'banyan_row' }, true)).toBe('Press ↑ to go into 3 Banyan Row.');
    expect(hintAt({ x: 24, y: 15, map: 'banyan_row' }, true)).toBe('Press ↑ to go to High Street.');
    expect(hintAt({ x: 18, y: 2, map: 'coffee_shop_floor_0' }, true)).toBe('Press ↑ to go out onto High Street.');
  });

  it('has nothing to say about stairs, ladders or lifts while E is used for something else', () => {
    expect(hintAt({ x: 15, y: 2, map: 'coffee_shop_floor_0' }, true)).toBeUndefined();
    expect(hintAt({ x: 45, y: 15, map: 'lychee_lane' }, true)).toBeUndefined();
    expect(hintAt({ x: 16, y: 2, map: 'gallery_floor_0' }, true)).toBeUndefined();
  });

  it('has nothing to say elsewhere, or partway up', () => {
    expect(hintAt({ x: 30, y: 15, map: 'high_street' })).toBeUndefined();
    const climbing = new SidePlayer(village, { x: 45, y: 15, map: 'lychee_lane' });
    climbing.update({ x: 0, y: 0, use: true }, 1 / 60);
    expect(climbing.way()).toBeUndefined();
  });
});
