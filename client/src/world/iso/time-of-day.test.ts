import { afterEach, describe, expect, it, vi } from 'vitest';
import type { SceneryManifest } from './manifest';
import { DEFAULT_SET, hourOf, LIGHTING_SETS, lightingSetAt, SimClock } from './time-of-day';

const manifests = import.meta.glob<SceneryManifest>('../../../../content/art/iso/scenery/*.json', {
  eager: true,
  import: 'default',
});

describe('lightingSetAt', () => {
  it('picks the set whose hours hold the sim time', () => {
    expect(lightingSetAt('2026-06-01T04:59:00')).toBe('night');
    expect(lightingSetAt('2026-06-01T05:00:00')).toBe('morning');
    expect(lightingSetAt('2026-06-01T12:30:00')).toBe('afternoon');
    expect(lightingSetAt('2026-06-01T17:00:00')).toBe('evening');
    expect(lightingSetAt('2026-06-01T21:00:00')).toBe('night');
    expect(lightingSetAt('2026-06-01T00:00:00')).toBe('night');
  });

  it('draws the afternoon until the sim time is known', () => {
    expect(DEFAULT_SET).toBe('afternoon');
    expect(lightingSetAt(undefined)).toBe('afternoon');
    expect(lightingSetAt('soon')).toBe('afternoon');
  });

  it('has the hours of every manifest', () => {
    const hours = Object.values(manifests).map(({ set, hours }) => [set, hours]);
    expect(Object.fromEntries(hours)).toEqual(LIGHTING_SETS);
  });
});

describe('hourOf', () => {
  it('reads the hour and minutes of a sim time', () => {
    expect(hourOf('2026-06-01T07:45:00')).toBe(7.75);
    expect(hourOf('2026-06-01T23:00:00.123456')).toBe(23);
  });
});

describe('SimClock', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('answers at once when it knows the time', async () => {
    const clock = new SimClock();
    clock.set('2026-06-01T08:00:00');
    await expect(clock.known(1000)).resolves.toBe('2026-06-01T08:00:00');
  });

  it('waits for the first time to arrive', async () => {
    vi.useFakeTimers();
    const clock = new SimClock();
    const known = clock.known(1000);
    vi.advanceTimersByTime(300);
    clock.set('2026-06-01T19:00:00');
    await expect(known).resolves.toBe('2026-06-01T19:00:00');
  });

  it('gives up after the timeout', async () => {
    vi.useFakeTimers();
    const clock = new SimClock();
    const known = clock.known(1000);
    vi.advanceTimersByTime(1000);
    await expect(known).resolves.toBeUndefined();
  });
});
