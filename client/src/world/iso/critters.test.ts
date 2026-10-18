import { describe, expect, it } from 'vitest';
import { village } from '../assets';
import { CRITTERS, Critters, Water, type Critter, type CritterTuning } from './critters';

const water = Water.of(village);
const FRAME = 1 / 30;

function seeded(seed: number): () => number {
  let state = seed;
  return () => {
    state = (state + 0x6d2b79f5) | 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const critters = (tuning: Partial<CritterTuning> = {}, seed = 1) =>
  new Critters(water, { ...CRITTERS, ...tuning }, seeded(seed));

function run(subject: Critters, seconds: number, hour: number, each: (all: readonly Critter[]) => void = () => {}) {
  subject.hour = hour;
  for (let t = 0; t < seconds; t += FRAME) {
    subject.update(FRAME);
    each(subject.all);
  }
}

const onWater = ({ kind, x, y, z }: Critter) =>
  kind === 'heron' ? z > 0 || water.roomy(x, y, 0.3) : water.roomy(x, y);
const gaps = (ducks: readonly Critter[]) =>
  ducks.flatMap((a, i) => ducks.slice(i + 1).map((b) => Math.hypot(a.x - b.x, a.y - b.y)));

describe('Water', () => {
  it('is the lake in the park and the river outside it', () => {
    expect(water.bodies.map(({ kind }) => kind).sort()).toEqual(['lake', 'river']);
    const lake = water.bodies.find(({ kind }) => kind === 'lake')!;
    const columns = lake.tiles.map((i) => i % water.width);
    expect(Math.min(...columns)).toBeGreaterThanOrEqual(46);
  });

  it('has a perch for the heron off the lake’s far shores only', () => {
    const [lake, river] = ['lake', 'river'].map((kind) => water.bodies.find((body) => body.kind === kind)!);
    expect(river.perches).toEqual([]);
    expect(lake.perches.length).toBeGreaterThan(0);
    for (let i = 0; i < lake.perches.length; i += 2) {
      const [x, y] = [lake.perches[i], lake.perches[i + 1]];
      expect(water.roomy(x, y, 0.3)).toBe(true);
      expect(water.isWater(x, y - 0.5) && water.isWater(x - 0.5, y)).toBe(false);
    }
  });

  it('keeps room for a critter only on water', () => {
    expect(water.roomy(58.5, 23.5)).toBe(true);
    expect(water.roomy(30.5, 20.5)).toBe(false);
    expect(water.roomy(58.5, 28.8)).toBe(false);
    expect(water.roomy(63.8, 23.5)).toBe(false);
  });
});

describe('Critters', () => {
  it('stay on water tiles, by day and at night', () => {
    for (const hour of [10, 14, 20.9, 23]) {
      const subject = critters({}, hour);
      run(subject, 600, hour, (all) => {
        for (const critter of all) if (critter.visible) expect(onWater(critter)).toBe(true);
      });
    }
  });

  it('put ducks on the lake and the river, and a heron by the lake', () => {
    const subject = critters();
    const ducks = subject.all.filter(({ kind }) => kind === 'duck');
    const lake = water.bodies.find(({ kind }) => kind === 'lake')!;
    const onLake = ducks.filter(({ x, y }) => lake.tiles.includes(Math.floor(y) * water.width + Math.floor(x)));
    expect(onLake).toHaveLength(CRITTERS.ducks.lake);
    expect(ducks).toHaveLength(CRITTERS.ducks.lake + CRITTERS.ducks.river);
    const seen = new Set<number>();
    run(subject, 1200, 10, (all) => all.forEach(({ kind, visible, z }) => kind === 'heron' && visible && seen.add(z)));
    expect(seen.has(0)).toBe(true);
  });

  it.each([0, 1, 3, 6, 7, 9, 12, 40])('never number more than a cap of %i', (cap) => {
    const subject = critters({ cap });
    expect(subject.all.length).toBeLessThanOrEqual(cap);
    let most = 0;
    run(subject, 300, 14, (all) => (most = Math.max(most, all.filter(({ visible }) => visible).length)));
    expect(most).toBeLessThanOrEqual(cap);
  });

  it('keep apart, and further from the heron', () => {
    const subject = critters({ heronAway: [1, 1] }, 7);
    const ducks = subject.all.filter(({ kind }) => kind === 'duck');
    const heron = subject.all.find(({ kind }) => kind === 'heron')!;
    let nearest = Infinity;
    let nearestHeron = Infinity;
    run(subject, 900, 12, () => {
      nearest = Math.min(nearest, ...gaps(ducks));
      if (heron.visible && heron.z === 0)
        nearestHeron = Math.min(nearestHeron, ...gaps([heron, ...ducks]).slice(0, ducks.length));
    });
    expect(nearest).toBeGreaterThan(0.75);
    expect(nearestHeron).toBeGreaterThan(1.35);
    expect(nearestHeron).toBeLessThan(Infinity);
  });

  it('settle at night: ducks tuck their heads in and sit still', () => {
    const subject = critters({}, 3);
    run(subject, 30, 14);
    const ducks = subject.all.filter(({ kind }) => kind === 'duck');
    run(subject, 1, 23);
    const where = ducks.map(({ x, y }) => [x, y]);
    run(subject, 120, 23, () => {
      for (const duck of ducks) {
        expect(duck.frame).toMatch(/-tucked-/);
        expect(duck.visible).toBe(true);
      }
    });
    expect(ducks.map(({ x, y }) => [x, y])).toEqual(where);
    run(subject, 60, 8);
    expect(ducks.some(({ frame }) => frame.includes('-tucked-'))).toBe(false);
    expect(ducks.map(({ x, y }) => [x, y])).not.toEqual(where);
  });

  it('settle each in their own time around nightfall', () => {
    const subject = critters({}, 4);
    const ducks = subject.all.filter(({ kind }) => kind === 'duck');
    const tucked = (hour: number) => {
      subject.hour = hour;
      subject.update(FRAME);
      return ducks.filter(({ frame }) => frame.includes('-tucked-')).length;
    };
    expect(tucked(20)).toBe(0);
    expect(tucked(21.5)).toBe(ducks.length);
    expect(tucked(4.9)).toBe(ducks.length);
    expect(tucked(6)).toBe(0);
  });

  it('see fish rise less often at night', () => {
    const rises = (hour: number) => {
      const subject = critters({ ducks: { lake: 0, river: 0 }, heron: false }, 5);
      let count = 0;
      let before = 0;
      run(subject, 900, hour, (all) => {
        const now = all.filter(({ frame, visible }) => visible && /koi|fish/.test(frame)).length;
        if (now > before) count += now - before;
        before = now;
      });
      return count;
    };
    expect(rises(23)).toBeLessThan(rises(13) / 2);
  });

  it('see the heron leave at nightfall and stay away until morning', () => {
    const subject = critters({ heronAway: [1, 1], heronStays: [600, 600] }, 2);
    const heron = subject.all.find(({ kind }) => kind === 'heron')!;
    run(subject, 30, 12);
    expect(heron.visible && heron.z).toBe(0);
    run(subject, 30, 22);
    expect(heron.visible).toBe(false);
    run(subject, 600, 3);
    expect(heron.visible).toBe(false);
  });
});
