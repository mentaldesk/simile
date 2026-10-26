import { describe, expect, it } from 'vitest';
import { village } from './content';
import { SidePlayer, type MapPosition } from './player';
import { prompts } from './ways';

const promptsOf = (position: MapPosition) => {
  const ways = new SidePlayer(village, position).ways();
  return prompts(village, village.map(position.map)!, ways);
};

const promptsAt = (position: MapPosition) =>
  promptsOf(position).map(({ keys, action }) => `${keys.join(' ')}: ${action}`);

describe('prompts', () => {
  it('give doors to E, saying where they go', () => {
    expect(promptsAt({ x: 43, y: 15, map: 'high_street' })).toEqual(['E: go in']);
    expect(promptsAt({ x: 18, y: 2, map: 'coffee_shop_floor_0' })).toEqual(['E: go out']);
    expect(promptsAt({ x: 46, y: 15, map: 'high_street' })).toEqual(['E: to Kapok Walk']);
    expect(promptsAt({ x: 24, y: 15, map: 'banyan_row' })).toEqual(['E: to High Street']);
  });

  it('give stairs and ladders between floors to up or down, whichever way they go', () => {
    expect(promptsAt({ x: 15, y: 2, map: 'coffee_shop_floor_0' })).toEqual(['↑: upstairs']);
    expect(promptsAt({ x: 18, y: 2, map: 'coffee_shop_floor_1' })).toEqual(['↓: downstairs']);
    expect(promptsAt({ x: 11, y: 2, map: 'coffee_shop_floor_1' })).toEqual(['↑: upstairs']);
    expect(promptsAt({ x: 6, y: 2, map: 'maker_space_floor_2' })).toEqual(['↓: climb down']);
  });

  it('show each way a key takes when two are in reach', () => {
    expect(promptsAt({ x: 6, y: 2, map: 'maker_space_floor_1' })).toEqual(['↑: climb up', '↓: downstairs']);
    expect(promptsAt({ x: 5, y: 2, map: 'maker_space_floor_1' })).toEqual(['↑: climb up', '↓: downstairs']);
    expect(promptsAt({ x: 4.4, y: 2, map: 'maker_space_floor_1' })).toEqual(['↓: downstairs']);
  });

  it('come up anywhere in the tile either side of the end of a flight or a ladder, and not beyond', () => {
    for (const x of [16, 16.4, 14, 13.6, 13.95]) {
      expect(promptsAt({ x, y: 2, map: 'coffee_shop_floor_0' }), `at ${x}`).toEqual(['↑: upstairs']);
    }
    expect(promptsAt({ x: 13.5, y: 2, map: 'coffee_shop_floor_0' })).toEqual([]);
    expect(promptsAt({ x: 43.6, y: 15, map: 'lychee_lane' })).toEqual(['↑: climb up']);
    expect(promptsAt({ x: 43.4, y: 15, map: 'lychee_lane' })).toEqual([]);
  });

  it('give a door on the cell beside the foot of the stairs to E, and the stairs to up', () => {
    expect(promptsAt({ x: 2, y: 2, map: 'noodle_bar_floor_0' })).toEqual(['E: go out', '↑: upstairs']);
    expect(promptsAt({ x: 3, y: 2, map: 'noodle_bar_floor_0' })).toEqual(['↑: upstairs']);
  });

  it('give the lift up and down from either of its cells, over its car', () => {
    expect(promptsAt({ x: 16, y: 2, map: 'gallery_floor_0' })).toEqual(['↑: lift']);
    expect(promptsAt({ x: 15, y: 2, map: 'gallery_floor_0' })).toEqual(['↑: lift']);
    expect(promptsAt({ x: 16, y: 2, map: 'gallery_floor_1' })).toEqual(['↑ ↓: lift']);
    expect(promptsAt({ x: 15, y: 2, map: 'gallery_floor_1' })).toEqual(['↑ ↓: lift']);
    expect(promptsAt({ x: 16, y: 2, map: 'gallery_floor_2' })).toEqual(['↓: lift']);
    expect(promptsAt({ x: 14, y: 2, map: 'gallery_floor_0' })).toEqual([]);
    expect(promptsOf({ x: 16, y: 2, map: 'gallery_floor_1' })[0].at).toEqual({ x: 15.5, y: 2 });
  });

  it('take stairs and ladders on a street from either end', () => {
    expect(promptsAt({ x: 53, y: 15, map: 'banyan_row' })).toEqual(['↓: down the steps']);
    expect(promptsAt({ x: 56, y: 18, map: 'banyan_row' })).toEqual(['↑: up the steps']);
    expect(promptsAt({ x: 45, y: 15, map: 'lychee_lane' })).toEqual(['↑: climb up']);
    expect(promptsAt({ x: 46, y: 12, map: 'lychee_lane' })).toEqual(['↓: climb down']);
  });

  it('give every door and every way onto another street to E, and none to up or down', () => {
    for (const map of village.maps.values()) {
      for (const door of map.links.filter(({ kind }) => kind === 'door')) {
        const player = Object.assign(new SidePlayer(village, { x: door.x, y: door.y, map: map.id }), { datajack: true });
        const here = prompts(village, map, player.ways());
        const keys = here.filter(({ way }) => way.kind === 'door').map(({ keys }) => keys);
        expect(keys, `${map.id} ${door.id}`).toEqual([['E']]);
      }
    }
  });

  it('give the stairs beside a door to up, and the door to E', () => {
    expect(promptsAt({ x: 2, y: 2, map: 'noodle_bar_floor_0' })).toEqual(['E: go out', '↑: upstairs']);
  });

  it('are none elsewhere, or partway up', () => {
    expect(promptsAt({ x: 30, y: 15, map: 'high_street' })).toEqual([]);
    const climbing = new SidePlayer(village, { x: 45, y: 15, map: 'lychee_lane' });
    climbing.update({ x: 0, y: -1, use: false, run: false }, 1 / 60);
    expect(climbing.climbing).toBe('ladder');
    expect(climbing.ways()).toEqual([]);
  });
});
