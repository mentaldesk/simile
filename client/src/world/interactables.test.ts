import { describe, expect, it, vi } from 'vitest';
import { maps } from './assets';
import { interactableAt, interactablesOf, InteractableWatch } from './interactables';
import { CollisionMap, type TiledMap } from './map';

const every = Object.entries(maps) as [string, TiledMap][];

describe('interactablesOf', () => {
  it('lists the counter at the Daily Grind, used from the front of the queue', () => {
    expect(interactablesOf('coffee_shop_floor_0', maps.coffee_shop_floor_0!)).toEqual([
      {
        id: 'coffee_shop_counter',
        kind: 'counter',
        label: 'Counter',
        map: 'coffee_shop_floor_0',
        area: { x: 3, y: 2, width: 3, height: 1 },
        stand: [{ x: 6, y: 2 }],
        prompt: 'Order at the counter',
      },
      {
        id: 'coffee_shop_plug',
        kind: 'plug',
        label: 'Plug',
        map: 'coffee_shop_floor_0',
        area: { x: 16, y: 2, width: 1, height: 1 },
        stand: [{ x: 16, y: 2 }],
        prompt: 'Plug',
      },
    ]);
  });

  it('prompts by kind', () => {
    const prompts = (map: string) => interactablesOf(map, maps[map]!).map(({ prompt }) => prompt);
    expect(prompts('maker_space_floor_0')).toEqual([
      'Use the laser cutter',
      'Use the 3D printer',
      'Use the loom',
      'Use the sewing machine',
      'Plug',
    ]);
    expect(new Set(prompts('gallery_floor_1'))).toEqual(new Set(['Look at the painting']));
  });

  it('has every stand tile walkable on its map', () => {
    for (const [id, map] of every) {
      const collision = CollisionMap.of(map);
      for (const { stand } of interactablesOf(id, map)) {
        expect(stand.length).toBeGreaterThan(0);
        for (const { x, y } of stand) expect(collision.blocks(x, y)).toBe(false);
      }
    }
  });
});

describe('interactableAt', () => {
  it('finds the interactable whose stand tile the player is on, as the server reads it', () => {
    expect(interactableAt('coffee_shop_floor_0', { x: 6, y: 2 })?.id).toBe('coffee_shop_counter');
    expect(interactableAt('coffee_shop_floor_0', { x: 6.4, y: 1.6 })?.id).toBe('coffee_shop_counter');
    expect(interactableAt('maker_space_floor_0', { x: 7, y: 2 })?.id).toBe('laser_cutter');
  });

  it('finds nothing off the stand tiles, on another map, or nowhere', () => {
    expect(interactableAt('nowhere', { x: 6, y: 2 })).toBeUndefined();
    expect(interactableAt('coffee_shop_floor_0', { x: 7, y: 2 })).toBeUndefined();
    expect(interactableAt('coffee_shop_floor_0', { x: 6.6, y: 2 })).toBeUndefined();
    expect(interactableAt('coffee_shop_floor_1', { x: 6, y: 2 })).toBeUndefined();
    expect(interactableAt('coffee_shop_floor_0', undefined)).toBeUndefined();
  });
});

describe('InteractableWatch', () => {
  it('tells listeners when the player steps onto a stand tile and off it, once each', () => {
    const watch = new InteractableWatch();
    const heard = vi.fn();
    const stop = watch.on(heard);
    const at = (x: number) => ({ x, y: 2, map: 'coffee_shop_floor_0' });
    watch.update(at(8));
    watch.update(at(6.2));
    watch.update(at(5.9));
    watch.update(at(7));
    expect(heard.mock.calls.map(([interactable]) => interactable?.prompt)).toEqual([
      'Order at the counter',
      undefined,
    ]);
    expect(watch.current).toBeUndefined();

    stop();
    watch.update(at(6));
    expect(heard).toHaveBeenCalledTimes(2);
    expect(watch.current?.id).toBe('coffee_shop_counter');
  });

  it('finds nothing for a position on no map', () => {
    const watch = new InteractableWatch();
    watch.update({ x: 6, y: 2 });
    expect(watch.current).toBeUndefined();
  });
});
