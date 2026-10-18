import { describe, expect, it, vi } from 'vitest';
import type { Door } from '../doors';
import {
  INTERIOR_KEEP_SECONDS,
  INTERIOR_NEAR_TILES,
  INTERIOR_RETRY_MAX_SECONDS,
  INTERIOR_RETRY_SECONDS,
  InteriorLoader,
  interiorsWanted,
} from './interiors';

const door = (to: string, x: number, y: number, map = 'village'): Door => ({
  id: to,
  map,
  x,
  y,
  to: { map: to, x: 10, y: 13 },
  out: { x: 0, y: 1 },
});

describe('interiorsWanted', () => {
  const doors = [door('gallery', 40, 33), door('coffee_shop', 31, 11)];

  it('wants the interior whose door the player is near', () => {
    expect(interiorsWanted({ x: 40, y: 34, map: 'village' }, doors)).toEqual(['gallery']);
    expect(interiorsWanted({ x: 40, y: 33 + INTERIOR_NEAR_TILES, map: 'village' }, doors)).toEqual(['gallery']);
    expect(interiorsWanted({ x: 40, y: 34 + INTERIOR_NEAR_TILES, map: 'village' }, doors)).toEqual([]);
  });

  it('wants the interior the player is in, but never the village', () => {
    const inside = [door('village', 10, 13, 'gallery')];
    expect(interiorsWanted({ x: 10, y: 12, map: 'gallery' }, inside)).toEqual(['gallery']);
  });
});

function loader() {
  const pending = new Map<string, { resolve: (scenery: string) => void; reject: (error: Error) => void }>();
  const load = vi.fn(
    (map: string) => new Promise<string>((resolve, reject) => pending.set(map, { resolve, reject })),
  );
  const unload = vi.fn();
  const interiors = new InteriorLoader(load, unload);
  const settle = async () => {
    await Promise.resolve();
    await Promise.resolve();
  };
  const finish = async (map: string) => {
    pending.get(map)!.resolve(`${map} scenery`);
    await settle();
  };
  const fail = async (map: string) => {
    pending.get(map)!.reject(new Error('404'));
    await settle();
  };
  return { interiors, load, unload, finish, fail };
}

const loads = (load: ReturnType<typeof vi.fn>) => load.mock.calls.map(([map]) => map);

describe('InteriorLoader', () => {
  it('loads an interior once it is wanted, and has it once loaded', async () => {
    const { interiors, load, finish } = loader();
    interiors.update(['gallery'], 0);
    interiors.update(['gallery'], 1);
    expect(interiors.get('gallery')).toBeUndefined();
    await finish('gallery');
    expect(interiors.get('gallery')).toBe('gallery scenery');
    expect([...interiors.loaded()]).toEqual(['gallery scenery']);
    expect(loads(load)).toEqual(['gallery']);
  });

  it('starts loading an interior a door leads to when asked for it', () => {
    const { interiors, load } = loader();
    expect(interiors.get('coffee_shop')).toBeUndefined();
    expect(loads(load)).toEqual(['coffee_shop']);
  });

  it(`keeps it while the player is in it, and unloads it ${INTERIOR_KEEP_SECONDS} s after they leave`, async () => {
    const { interiors, unload, finish } = loader();
    interiors.update(['gallery'], 0);
    await finish('gallery');
    interiors.update(['gallery'], 1000);
    interiors.update([], 1000 + INTERIOR_KEEP_SECONDS - 0.1);
    expect(unload).not.toHaveBeenCalled();
    interiors.update([], 1000 + INTERIOR_KEEP_SECONDS);
    expect(unload).toHaveBeenCalledExactlyOnceWith('gallery', 'gallery scenery');
    expect(interiors.get('gallery')).toBeUndefined();
    expect([...interiors.loaded()]).toEqual([]);
  });

  it('loads it again when the player comes back', async () => {
    const { interiors, load, finish } = loader();
    interiors.update(['gallery'], 0);
    await finish('gallery');
    interiors.update([], INTERIOR_KEEP_SECONDS);
    interiors.update(['gallery'], INTERIOR_KEEP_SECONDS + 60);
    expect(loads(load)).toEqual(['gallery', 'gallery']);
    await finish('gallery');
    expect(interiors.get('gallery')).toBe('gallery scenery');
  });

  it('keeps one the player comes back to before it goes', async () => {
    const { interiors, load, unload, finish } = loader();
    interiors.update(['gallery'], 0);
    await finish('gallery');
    interiors.update([], 10);
    interiors.update(['gallery'], 20);
    interiors.update([], 20 + INTERIOR_KEEP_SECONDS - 1);
    expect(unload).not.toHaveBeenCalled();
    expect(loads(load)).toEqual(['gallery']);
  });

  it('backs off before trying a failed interior again, longer each time', async () => {
    const { interiors, load, fail, finish } = loader();
    vi.spyOn(console, 'error').mockImplementation(() => {});
    interiors.update(['gallery'], 0);
    await fail('gallery');
    interiors.update(['gallery'], INTERIOR_RETRY_SECONDS - 0.1);
    expect(loads(load)).toEqual(['gallery']);

    interiors.update(['gallery'], INTERIOR_RETRY_SECONDS);
    expect(loads(load)).toEqual(['gallery', 'gallery']);
    await fail('gallery');
    interiors.update(['gallery'], 3 * INTERIOR_RETRY_SECONDS - 0.1);
    expect(loads(load)).toHaveLength(2);
    interiors.update(['gallery'], 3 * INTERIOR_RETRY_SECONDS);
    expect(loads(load)).toHaveLength(3);

    await finish('gallery');
    expect(interiors.get('gallery')).toBe('gallery scenery');
  });

  it(`waits no more than ${INTERIOR_RETRY_MAX_SECONDS} s between tries`, async () => {
    const { interiors, load, fail } = loader();
    vi.spyOn(console, 'error').mockImplementation(() => {});
    let now = 0;
    for (let tries = 1; tries <= 12; tries++) {
      interiors.update(['gallery'], now);
      expect(loads(load)).toHaveLength(tries);
      await fail('gallery');
      now += INTERIOR_RETRY_MAX_SECONDS;
    }
  });

  it('unloads every interior on a reset, and drops those still loading when they finish', async () => {
    const { interiors, load, unload, finish } = loader();
    interiors.update(['gallery', 'coffee_shop'], 0);
    await finish('gallery');
    interiors.reset();
    expect(unload).toHaveBeenCalledExactlyOnceWith('gallery', 'gallery scenery');

    interiors.update(['coffee_shop'], 1);
    expect(loads(load)).toEqual(['gallery', 'coffee_shop']);
    await finish('coffee_shop');
    expect(unload).toHaveBeenLastCalledWith('coffee_shop', 'coffee_shop scenery');
    expect(interiors.get('coffee_shop')).toBeUndefined();

    interiors.update(['gallery'], 2);
    expect(loads(load)).toEqual(['gallery', 'coffee_shop', 'coffee_shop', 'gallery']);
  });
});
