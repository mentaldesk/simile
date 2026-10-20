import { describe, expect, it } from 'vitest';
import { SideClock, hourOf } from './clock';
import { scenery } from './content';
import { colour, emptyLight, FOREGROUND_SHADE, hazeOf, INSIDE, layerTint, lightAt, overflow, timesAt } from './light';
import type { Rgb } from './scenery';

const { times } = scenery;

describe('the time of day', () => {
  it('is each of the four times between their changes', () => {
    expect(timesAt(8)).toEqual({ from: 'morning', to: 'morning', weight: 0 });
    expect(timesAt(14)).toEqual({ from: 'afternoon', to: 'afternoon', weight: 0 });
    expect(timesAt(19)).toEqual({ from: 'evening', to: 'evening', weight: 0 });
    expect(timesAt(2)).toEqual({ from: 'night', to: 'night', weight: 0 });
    expect(timesAt(23.9)).toEqual({ from: 'night', to: 'night', weight: 0 });
  });

  it('fades from one to the next across each change', () => {
    expect(timesAt(17)).toEqual({ from: 'afternoon', to: 'evening', weight: 0.5 });
    expect(timesAt(21.25).from).toBe('evening');
    expect(timesAt(21.25).weight).toBeGreaterThan(0.5);
    expect(timesAt(4.9)).toMatchObject({ from: 'night', to: 'morning' });
  });

  it("takes each time's tint, sky, haze and glow from the manifest", () => {
    const night = lightAt(2, scenery);
    expect(night.tint).toEqual(times.night.tint);
    expect(night.sky).toEqual(times.night.sky);
    expect(night.glow).toBe(1);
    expect(night.hazeAmount).toBe(times.night.haze[0]);
    expect(night.haze.map((c) => Math.round(c * 255))).toEqual(times.night.haze.slice(1));
    expect(night.inside).toEqual(INSIDE.night);
    expect(lightAt(19, scenery).glow).toBe(0.55);
    expect(lightAt(14, scenery).glow).toBe(0);
  });

  it('changes smoothly, a sim minute at a time, all day', () => {
    let last = lightAt(0, scenery, emptyLight());
    for (let minute = 1; minute <= 24 * 60; minute++) {
      const light = lightAt(minute / 60, scenery);
      for (let i = 0; i < 3; i++) expect(Math.abs(light.tint[i] - last.tint[i])).toBeLessThan(0.03);
      expect(Math.abs(light.glow - last.glow)).toBeLessThan(0.05);
      last = light;
    }
  });
});

describe('tints by layer depth', () => {
  const light = lightAt(19, scenery);
  const out: Rgb = [0, 0, 0];

  it('gives the sky its own tint and the near layers the time tint', () => {
    expect(layerTint(light, 'sky', out)).toEqual(light.sky);
    expect(layerTint(light, 'near', out)).toEqual(light.tint);
    expect(layerTint(light, 'ground', out)).toEqual(light.tint);
  });

  it('pulls distant layers towards the sky', () => {
    const far = [...layerTint(light, 'far', out)];
    const mid = [...layerTint(light, 'mid', out)];
    for (let i = 0; i < 3; i++) {
      expect(far[i]).toBeCloseTo((light.tint[i] + light.sky[i]) / 2);
      expect(Math.abs(mid[i] - light.tint[i])).toBeLessThanOrEqual(Math.abs(far[i] - light.tint[i]) + 1e-9);
    }
  });

  it('darkens the foreground and hazes the far layer twice the mid', () => {
    expect(layerTint(light, 'foreground', out)[1]).toBeCloseTo(light.tint[1] * FOREGROUND_SHADE);
    expect(hazeOf(light, 'far')).toBeCloseTo(2 * hazeOf(light, 'mid'));
    expect(hazeOf(light, 'near')).toBe(0);
  });

  it('turns a tint into a Phaser colour, with what is over 1 left to add', () => {
    expect(colour([1, 0.5, 0])).toBe(0xff8000);
    expect(colour([1.2, -1, 0.2])).toBe(0xff0033);
    expect(overflow([1.08, 0.9, 1])).toBe(0x140000);
  });
});

describe('the sim clock', () => {
  it('reads the hour of a sim time', () => {
    expect(hourOf('2026-03-14T09:30:00Z')).toBe(9.5);
    expect(hourOf('nonsense')).toBeUndefined();
  });

  it('runs on at its speed between readings', () => {
    let now = 0;
    const clock = new SideClock(() => now);
    expect(clock.hour()).toBe(14);
    clock.set('2026-03-14T23:00:00Z', 60);
    now = 90_000;
    expect(clock.hour()).toBeCloseTo(0.5);
  });
});
