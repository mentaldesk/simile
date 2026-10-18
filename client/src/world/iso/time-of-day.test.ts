import { afterEach, describe, expect, it, vi } from 'vitest';
import type { SceneryManifest } from './manifest';
import {
  blend,
  CROSSFADE_MINUTES,
  hourOf,
  LIGHTING_SETS,
  nextSet,
  SimClock,
  type Layer,
} from './time-of-day';

const manifests = import.meta.glob<SceneryManifest & { crossfade_minutes: number }>(
  '../../../../content/art/iso/scenery/*.json',
  { eager: true, import: 'default' },
);

/** `simile.art.iso.lighting.blend(hour)`, printed by Python. */
const FROM_LIGHTING_PY: [number, [string, number][]][] = [
  [0, [['night', 1.0]]],
  [4.4, [['night', 1.0]]],
  [4.5, [['night', 1.0]]],
  [4.75, [['night', 0.84375], ['morning', 0.15625]]],
  [5, [['night', 0.5], ['morning', 0.5]]],
  [5.25, [['night', 0.15625], ['morning', 0.84375]]],
  [5.5, [['morning', 1.0]]],
  [8, [['morning', 1.0]]],
  [10.6, [['morning', 0.972], ['afternoon', 0.028]]],
  [11, [['morning', 0.5], ['afternoon', 0.5]]],
  [11.4, [['morning', 0.028], ['afternoon', 0.972]]],
  [14, [['afternoon', 1.0]]],
  [16.5, [['afternoon', 1.0]]],
  [16.9, [['afternoon', 0.648], ['evening', 0.352]]],
  [17, [['afternoon', 0.5], ['evening', 0.5]]],
  [17.2, [['afternoon', 0.216], ['evening', 0.784]]],
  [19, [['evening', 1.0]]],
  [20.5, [['evening', 1.0]]],
  [20.75, [['evening', 0.84375], ['night', 0.15625]]],
  [21, [['evening', 0.5], ['night', 0.5]]],
  [21.3, [['evening', 0.104], ['night', 0.896]]],
  [21.5, [['night', 1.0]]],
  [23.9, [['night', 1.0]]],
];

const rounded = (layers: Layer[]) => layers.map(({ set, weight }) => [set, Number(weight.toFixed(6))]);

describe('blend', () => {
  it.each(FROM_LIGHTING_PY)('matches lighting.py at %f h', (hour, expected) => {
    expect(rounded(blend(hour))).toEqual(expected);
  });

  it('fades without a jump across each boundary', () => {
    for (const [start] of Object.values(LIGHTING_SETS)) {
      for (const edge of [start - 0.5, start + 0.5]) {
        const weightOf = (hour: number, set: string) =>
          blend(hour).find((layer) => layer.set === set)?.weight ?? 0;
        const [before, after] = [blend(edge - 1e-6), blend(edge + 1e-6)];
        for (const { set } of [...before, ...after]) {
          expect(weightOf(edge - 1e-6, set)).toBeCloseTo(weightOf(edge + 1e-6, set), 4);
        }
      }
    }
  });

  it('wraps past midnight and around the clock', () => {
    expect(blend(24.25)).toEqual(blend(0.25));
    expect(blend(-3)).toEqual(blend(21));
  });

  it('has the hours and crossfade of every manifest', () => {
    const hours = Object.values(manifests).map(({ set, hours }) => [set, hours]);
    expect(Object.fromEntries(hours)).toEqual(LIGHTING_SETS);
    for (const manifest of Object.values(manifests)) {
      expect(manifest.crossfade_minutes).toBe(CROSSFADE_MINUTES);
    }
  });
});

describe('nextSet', () => {
  it('is the set the next fade brings in, once it starts within the hours ahead', () => {
    expect(nextSet(14, 0)).toBeUndefined();
    expect(nextSet(14, 2.4)).toBeUndefined();
    expect(nextSet(14, 2.5)).toBe('evening');
    expect(nextSet(14, 24)).toBe('evening');
  });

  it('is nothing while a fade is under way, and wraps past midnight', () => {
    expect(nextSet(17, 24)).toBeUndefined();
    expect(nextSet(23, 6)).toBe('morning');
    expect(nextSet(23, 5)).toBeUndefined();
  });
});

describe('hourOf', () => {
  it('reads the hour, minutes and seconds of a sim time', () => {
    expect(hourOf('2026-06-01T07:45:00')).toBe(7.75);
    expect(hourOf('2026-06-01T07:45:36Z')).toBeCloseTo(7.76);
    expect(hourOf('2026-06-01T23:00:00.123456+00:00')).toBeCloseTo(23);
    expect(hourOf('2026-06-01T08:30')).toBe(8.5);
    expect(hourOf('soon')).toBeUndefined();
  });
});

describe('SimClock', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  function clockAt(ms: { now: number }) {
    return new SimClock(() => ms.now);
  }

  it("doesn't know the hour until the server sends the time", () => {
    const clock = clockAt({ now: 0 });
    expect(clock.hour()).toBeUndefined();
    clock.set('soon');
    expect(clock.hour()).toBeUndefined();
  });

  it('runs on from the last time at its speed', () => {
    const real = { now: 5000 };
    const clock = clockAt(real);
    clock.set('2026-06-01T20:00:00', 60);
    real.now += 30_000;
    expect(clock.hour()).toBeCloseTo(20.5);
    real.now += 60_000;
    expect(clock.hour()).toBeCloseTo(21.5);
  });

  it('keeps the speed through a snapshot, which has none', () => {
    const real = { now: 0 };
    const clock = clockAt(real);
    clock.set('2026-06-01T08:00:00', 10);
    clock.set('2026-06-01T09:00:00');
    real.now += 360_000;
    expect(clock.hour()).toBeCloseTo(10);
  });

  it('runs on past midnight', () => {
    const real = { now: 0 };
    const clock = clockAt(real);
    clock.set('2026-06-01T23:30:00', 3600);
    real.now += 1000;
    expect(clock.hour()).toBeCloseTo(0.5);
  });

  it('answers at once when it knows the time', async () => {
    const clock = clockAt({ now: 0 });
    clock.set('2026-06-01T08:00:00');
    await expect(clock.known(1000)).resolves.toBeUndefined();
  });

  it('waits for the first time to arrive, or gives up', async () => {
    vi.useFakeTimers();
    const clock = clockAt({ now: 0 });
    const arrived = vi.fn();
    void clock.known(1000).then(arrived);
    vi.advanceTimersByTime(300);
    clock.set('2026-06-01T19:00:00');
    await vi.waitFor(() => expect(arrived).toHaveBeenCalled());

    const never = new SimClock();
    const gaveUp = vi.fn();
    void never.known(1000).then(gaveUp);
    vi.advanceTimersByTime(999);
    await Promise.resolve();
    expect(gaveUp).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    await vi.waitFor(() => expect(gaveUp).toHaveBeenCalled());
  });
});
