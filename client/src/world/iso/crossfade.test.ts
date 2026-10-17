import { describe, expect, it, vi } from 'vitest';
import { layerAlphas, PAIR_DEPTH, PRELOAD_SECONDS, SetLoader } from './crossfade';
import { residentDepth } from './depth';
import type { Layer, LightingSet } from './time-of-day';

const fade = (incoming: number): Layer[] => [
  { set: 'afternoon', weight: 1 - incoming },
  { set: 'evening', weight: incoming },
];

/** Composites the pair over what's behind, outgoing first, as the GPU does: `edge` is pixel alpha. */
function composite(
  layers: Layer[],
  alpha: number,
  [outgoing, incoming, behind]: number[],
  edge = 1,
): number {
  const [a, b] = layerAlphas(layers, alpha).map((each) => each * edge);
  const over = a * outgoing + (1 - a) * behind;
  return b * incoming + (1 - b) * over;
}

describe('layerAlphas', () => {
  it('draws one set at the alpha it is given', () => {
    expect(layerAlphas([{ set: 'night', weight: 1 }])).toEqual([1]);
    expect(layerAlphas([{ set: 'night', weight: 1 }], 0.3)).toEqual([0.3]);
  });

  it('draws the outgoing opaque and the incoming over it at its weight', () => {
    expect(layerAlphas(fade(0.25))).toEqual([1, 0.25]);
    expect(layerAlphas(fade(0.9))).toEqual([1, 0.9]);
    expect(layerAlphas(fade(1))).toEqual([0, 1]);
  });

  it.each([0, 0.2, 0.5, 0.9, 1])('mixes the pair by weight, faded with the cutaway, at %f', (incoming) => {
    for (const alpha of [1, 0.6, 0.3]) {
      const mixed = composite(fade(incoming), alpha, [0.8, 0.2, 0.5]);
      const wanted = alpha * (incoming * 0.2 + (1 - incoming) * 0.8) + (1 - alpha) * 0.5;
      expect(mixed).toBeCloseTo(wanted);
    }
  });

  it("lets at most 2% of what's behind through as the outgoing image goes", () => {
    for (let incoming = 0.9; incoming <= 1; incoming += 0.001) {
      const mixed = composite(fade(incoming), 1, [0.8, 0.8, 0]);
      expect(mixed).toBeGreaterThan(0.8 * 0.98);
    }
  });

  it('starts and ends the fade with soft edges as one image alone draws them', () => {
    const alone = (colour: number, edge: number) => edge * colour + (1 - edge) * 0.5;
    for (const edge of [0.25, 0.5, 0.75]) {
      expect(composite(fade(1e-9), 1, [1, 0, 0.5], edge)).toBeCloseTo(alone(1, edge));
      expect(composite(fade(1 - 1e-9), 1, [1, 0, 0.5], edge)).toBeCloseTo(alone(0, edge));
    }
  });

  it('keeps the incoming image of a pair behind a resident who ties with it', () => {
    const tile = { width: 96, height: 48, px_per_metre_up: 53.443 };
    const feet = { x: 10.5, y: 4.5 };
    const slice = residentDepth(feet, tile) - 1e-3;
    expect(slice + PAIR_DEPTH).toBeLessThan(residentDepth(feet, tile));
    expect(slice + PAIR_DEPTH).toBeGreaterThan(slice);
  });
});

function loader() {
  const pending = new Map<LightingSet, { resolve: () => void; reject: (error: Error) => void }>();
  const load = vi.fn(
    (set: LightingSet) => new Promise<void>((resolve, reject) => pending.set(set, { resolve, reject })),
  );
  const unload = vi.fn();
  const sets = new SetLoader(load, unload);
  const finish = async (set: LightingSet) => {
    pending.get(set)!.resolve();
    await Promise.resolve();
  };
  return { sets, load, unload, pending, finish };
}

const loads = (load: ReturnType<typeof vi.fn>) => load.mock.calls.map(([set]) => set);

describe('SetLoader', () => {
  it('draws nothing until every set the hour needs has loaded', async () => {
    const { sets, load, finish } = loader();
    expect(sets.update(11.2, 1)).toEqual([]);
    expect(loads(load)).toEqual(['morning', 'afternoon']);
    await finish('afternoon');
    expect(sets.update(11.2, 1)).toEqual([]);
    await finish('morning');
    expect(sets.update(11.2, 1).map(({ set }) => set)).toEqual(['morning', 'afternoon']);
  });

  it('loads only the set in use while no fade is near', async () => {
    const { sets, load, finish } = loader();
    sets.update(14, 1);
    await finish('afternoon');
    expect(sets.update(14, 1)).toEqual([{ set: 'afternoon', weight: 1 }]);
    expect(loads(load)).toEqual(['afternoon']);
  });

  it(`loads the next set ${PRELOAD_SECONDS} s before its fade, by the clock's speed`, async () => {
    const { sets, load, finish } = loader();
    const fadeStarts = 16.5;
    const lead = (speed: number) => (speed * PRELOAD_SECONDS) / 3600;
    sets.update(14, 1);
    await finish('afternoon');

    sets.update(fadeStarts - lead(1) - 0.01, 1);
    expect(loads(load)).toEqual(['afternoon']);
    sets.update(fadeStarts - lead(1) + 0.01, 1);
    expect(loads(load)).toEqual(['afternoon', 'evening']);

    const fast = loader();
    fast.sets.update(14, 60);
    expect(loads(fast.load)).toEqual(['afternoon']);
    fast.sets.update(fadeStarts - lead(60) + 0.01, 60);
    expect(loads(fast.load)).toEqual(['afternoon', 'evening']);
  });

  it('draws both sets through the fade, then unloads the outgoing one', async () => {
    const { sets, unload, finish } = loader();
    sets.update(16.49, 1);
    await finish('afternoon');
    await finish('evening');
    expect(sets.update(16.49, 1)).toEqual([{ set: 'afternoon', weight: 1 }]);

    const mid = sets.update(17, 1);
    expect(mid).toEqual([
      { set: 'afternoon', weight: 0.5 },
      { set: 'evening', weight: 0.5 },
    ]);
    sets.update(17.49, 1);
    expect(unload).not.toHaveBeenCalled();

    expect(sets.update(17.51, 1)).toEqual([{ set: 'evening', weight: 1 }]);
    expect(unload).toHaveBeenCalledExactlyOnceWith('afternoon');
  });

  it('keeps drawing the old set after a jump until the new ones have loaded', async () => {
    const { sets, unload, finish, load } = loader();
    sets.update(8, 1);
    await finish('morning');
    expect(sets.update(8, 1)).toEqual([{ set: 'morning', weight: 1 }]);

    expect(sets.update(20.75, 1)).toEqual([{ set: 'morning', weight: 1 }]);
    expect(loads(load)).toEqual(['morning', 'evening', 'night']);
    await finish('night');
    expect(sets.update(20.75, 1)).toEqual([{ set: 'morning', weight: 1 }]);
    await finish('evening');
    expect(sets.update(20.75, 1).map(({ set }) => set)).toEqual(['evening', 'night']);
    expect(unload).toHaveBeenCalledExactlyOnceWith('morning');
  });

  it('unloads a set that finishes loading after the clock has moved past it', async () => {
    const { sets, unload, finish } = loader();
    sets.update(14, 1);
    await finish('afternoon');
    sets.update(16.49, 1);
    sets.update(23, 1);
    await finish('night');
    await finish('evening');
    expect(sets.update(23, 1)).toEqual([{ set: 'night', weight: 1 }]);
    expect(unload.mock.calls.map(([set]) => set).sort()).toEqual(['afternoon', 'evening']);
  });

  it("leaves out a set that couldn't load, and doesn't try it again", async () => {
    const { sets, load, pending, finish } = loader();
    vi.spyOn(console, 'error').mockImplementation(() => {});
    sets.update(17, 1);
    await finish('afternoon');
    pending.get('evening')!.reject(new Error('404'));
    await Promise.resolve();
    await Promise.resolve();
    expect(sets.update(17, 1)).toEqual([{ set: 'afternoon', weight: 1 }]);
    sets.update(17.1, 1);
    expect(loads(load)).toEqual(['afternoon', 'evening']);
  });
});
