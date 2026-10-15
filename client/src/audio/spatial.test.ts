import { describe, expect, it } from 'vitest';
import { FULL_VOLUME_WITHIN, SILENT_BEYOND, spatialMix } from './spatial';

const listener = { x: 10, y: 10 };
const at = (dx: number, dy = 0) => spatialMix(listener, { x: 10 + dx, y: 10 + dy });

describe('spatialMix', () => {
  it('plays a speaker on top of the listener at full volume, centred', () => {
    expect(at(0)).toEqual({ gain: 1, pan: 0 });
  });

  it('keeps full volume close by', () => {
    expect(at(0, FULL_VOLUME_WITHIN).gain).toBe(1);
    expect(at(-1.2, 1.2).gain).toBe(1);
  });

  it('gets quieter with distance in any direction', () => {
    const distances = [2, 3, 5, 8, 11, 13.5];
    const gains = distances.map((distance) => at(distance).gain);

    expect(gains).toEqual([...gains].sort((a, b) => b - a));
    expect(new Set(gains).size).toBe(gains.length);
    expect(at(0, -5).gain).toBeCloseTo(at(5).gain, 12);
    expect(at(3, 4).gain).toBeCloseTo(at(-5).gain, 12);
  });

  it('is silent at the edge of hearing and beyond', () => {
    expect(at(SILENT_BEYOND).gain).toBe(0);
    expect(at(0, 40).gain).toBe(0);
  });

  it('pans towards the side the speaker is on', () => {
    expect(at(4).pan).toBeGreaterThan(0);
    expect(at(-4).pan).toBeCloseTo(-at(4).pan, 12);
    expect(at(0, 6).pan).toBe(0);
    expect(at(0, -6).pan).toBe(0);
  });

  it('pans by direction, not distance, once out of arm’s reach', () => {
    expect(at(3, 4).pan).toBeCloseTo(at(6, 8).pan, 12);
    expect(at(3, 4).pan).toBeLessThan(at(5).pan);
  });

  it('pans less for a speaker almost on top of the listener', () => {
    expect(Math.abs(at(0.5).pan)).toBeLessThan(Math.abs(at(4).pan));
  });

  it('never pans fully to one ear', () => {
    for (const dx of [-100, -3, -0.1, 0.1, 3, 100]) {
      expect(Math.abs(at(dx).pan)).toBeLessThan(1);
    }
  });
});
