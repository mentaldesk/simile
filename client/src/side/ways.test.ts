import { describe, expect, it } from 'vitest';
import { village } from './content';
import { SidePlayer, type MapPosition } from './player';
import { prompts } from './ways';

const promptsAt = (position: MapPosition, eTaken = false) => {
  const ways = new SidePlayer(village, position).ways();
  const found = prompts(village, village.map(position.map)!, ways, eTaken);
  return found.map(({ keys, action }) => `${keys.join(' ')}: ${action}`);
};

describe('prompts', () => {
  it('name the keys that take a door and where it goes', () => {
    expect(promptsAt({ x: 43, y: 15, map: 'high_street' })).toEqual(['E ↑: go in']);
    expect(promptsAt({ x: 18, y: 2, map: 'coffee_shop_floor_0' })).toEqual(['E ↑: go out']);
    expect(promptsAt({ x: 46, y: 15, map: 'high_street' })).toEqual(['E ↑: to Kapok Walk']);
    expect(promptsAt({ x: 24, y: 15, map: 'banyan_row' })).toEqual(['E ↑: to High Street']);
  });

  it('say which way stairs and ladders between floors go, and take up or down without E', () => {
    expect(promptsAt({ x: 15, y: 2, map: 'coffee_shop_floor_0' })).toEqual(['E ↑: upstairs']);
    expect(promptsAt({ x: 18, y: 2, map: 'coffee_shop_floor_1' })).toEqual(['E ↓: downstairs']);
    expect(promptsAt({ x: 11, y: 2, map: 'coffee_shop_floor_1' })).toEqual(['E ↑: upstairs']);
    expect(promptsAt({ x: 6, y: 2, map: 'maker_space_floor_2' })).toEqual(['E ↓: climb down']);
  });

  it('show each way a key takes when two are in reach', () => {
    expect(promptsAt({ x: 6, y: 2, map: 'maker_space_floor_1' })).toEqual(['E ↑: climb up', '↓: downstairs']);
    expect(promptsAt({ x: 5, y: 2, map: 'maker_space_floor_1' })).toEqual(['E ↓: downstairs', '↑: climb up']);
  });

  it('come up within a tile of the end of a flight or a ladder, and not beyond', () => {
    expect(promptsAt({ x: 16, y: 2, map: 'coffee_shop_floor_0' })).toEqual(['E ↑: upstairs']);
    expect(promptsAt({ x: 14, y: 2, map: 'coffee_shop_floor_0' })).toEqual(['E ↑: upstairs']);
    expect(promptsAt({ x: 13.9, y: 2, map: 'coffee_shop_floor_0' })).toEqual([]);
    expect(promptsAt({ x: 44, y: 15, map: 'lychee_lane' })).toEqual(['E ↑: climb up']);
  });

  it('keep a door to the cell it is on, ahead of stairs a tile away', () => {
    expect(promptsAt({ x: 2, y: 2, map: 'noodle_bar_floor_0' })).toEqual(['E ↑: go out']);
    expect(promptsAt({ x: 3, y: 2, map: 'noodle_bar_floor_0' })).toEqual(['E ↑: upstairs']);
  });

  it('say which floor each end of a lift goes to, only on its cell', () => {
    expect(promptsAt({ x: 16, y: 2, map: 'gallery_floor_0' })).toEqual(['E: lift to the first floor']);
    expect(promptsAt({ x: 15, y: 2, map: 'gallery_floor_0' })).toEqual(['E: lift to the second floor']);
    expect(promptsAt({ x: 16, y: 2, map: 'gallery_floor_2' })).toEqual(['E: lift to the ground floor']);
    expect(promptsAt({ x: 14, y: 2, map: 'gallery_floor_0' })).toEqual([]);
  });

  it('take stairs and ladders on a street from either end', () => {
    expect(promptsAt({ x: 53, y: 15, map: 'banyan_row' })).toEqual(['E ↓: down the steps']);
    expect(promptsAt({ x: 56, y: 18, map: 'banyan_row' })).toEqual(['E ↑: up the steps']);
    expect(promptsAt({ x: 45, y: 15, map: 'lychee_lane' })).toEqual(['E ↑: climb up']);
    expect(promptsAt({ x: 46, y: 12, map: 'lychee_lane' })).toEqual(['E ↓: climb down']);
  });

  it('leave E off while it is used for something in reach', () => {
    expect(promptsAt({ x: 17, y: 15, map: 'banyan_row' }, true)).toEqual(['↑: go in']);
    expect(promptsAt({ x: 18, y: 2, map: 'coffee_shop_floor_0' }, true)).toEqual(['↑: go out']);
    expect(promptsAt({ x: 15, y: 2, map: 'coffee_shop_floor_0' }, true)).toEqual(['↑: upstairs']);
    expect(promptsAt({ x: 16, y: 2, map: 'gallery_floor_0' }, true)).toEqual([]);
  });

  it('are none elsewhere, or partway up', () => {
    expect(promptsAt({ x: 30, y: 15, map: 'high_street' })).toEqual([]);
    const climbing = new SidePlayer(village, { x: 45, y: 15, map: 'lychee_lane' });
    climbing.update({ x: 0, y: 0, use: true }, 1 / 60);
    expect(climbing.ways()).toEqual([]);
  });
});
