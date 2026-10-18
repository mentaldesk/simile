import { describe, expect, it, vi } from 'vitest';
import { interactableAt, interactablesOf, InteractableWatch } from './interactables';
import { CollisionMap } from './map';
import { loadEveryMap } from './maps.fixture';

const maps = await loadEveryMap();

describe('interactablesOf', () => {
  it('lists the counter at the Daily Grind, used from the front of the queue', () => {
    expect(interactablesOf('coffee_shop', maps.coffee_shop)).toEqual([
      {
        id: 'coffee_shop_counter',
        kind: 'counter',
        label: 'Counter',
        map: 'coffee_shop',
        stand: [{ x: 5, y: 6 }],
        prompt: 'Order at the counter',
      },
    ]);
  });

  it('prompts by kind', () => {
    const prompts = (map: string) => interactablesOf(map, maps[map]).map(({ prompt }) => prompt);
    expect(prompts('maker_space')).toEqual([
      'Use the laser cutter',
      'Use the 3D printer',
      'Use the loom',
      'Use the sewing machine',
    ]);
    expect(new Set(prompts('gallery'))).toEqual(new Set(['Look at the painting']));
  });

  it('has every stand tile walkable on its map', () => {
    for (const [id, map] of Object.entries(maps)) {
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
    expect(interactableAt('coffee_shop', { x: 5, y: 6 })?.id).toBe('coffee_shop_counter');
    expect(interactableAt('coffee_shop', { x: 5.4, y: 5.6 })?.id).toBe('coffee_shop_counter');
    expect(interactableAt('maker_space', { x: 3, y: 3 })?.id).toBe('laser_cutter');
  });

  it('finds nothing off the stand tiles, on another map, or nowhere', () => {
    expect(interactableAt('nowhere', { x: 5, y: 6 })).toBeUndefined();
    expect(interactableAt('coffee_shop', { x: 5, y: 7 })).toBeUndefined();
    expect(interactableAt('coffee_shop', { x: 5.6, y: 6 })).toBeUndefined();
    expect(interactableAt('village', { x: 5, y: 6 })).toBeUndefined();
    expect(interactableAt('coffee_shop', undefined)).toBeUndefined();
  });
});

describe('InteractableWatch', () => {
  it('tells listeners when the player steps onto a stand tile and off it, once each', () => {
    const watch = new InteractableWatch();
    const heard = vi.fn();
    const stop = watch.on(heard);
    watch.update({ x: 5, y: 8, map: 'coffee_shop' });
    watch.update({ x: 5, y: 6.2, map: 'coffee_shop' });
    watch.update({ x: 5.1, y: 6, map: 'coffee_shop' });
    watch.update({ x: 5, y: 7, map: 'coffee_shop' });
    expect(heard.mock.calls.map(([interactable]) => interactable?.prompt)).toEqual([
      'Order at the counter',
      undefined,
    ]);
    expect(watch.current).toBeUndefined();

    stop();
    watch.update({ x: 5, y: 6, map: 'coffee_shop' });
    expect(heard).toHaveBeenCalledTimes(2);
    expect(watch.current?.id).toBe('coffee_shop_counter');
  });

  it('reads a position with no map as the village', () => {
    const watch = new InteractableWatch();
    watch.update({ x: 5, y: 6 });
    expect(watch.current).toBeUndefined();
  });
});
