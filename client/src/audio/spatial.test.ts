import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import type { Position } from '../net';
import { loadStreets } from '../ui/street.fixture';
import {
  FULL_VOLUME_WITHIN,
  OVERHEARD_GAIN,
  overheardMix,
  partnerMix,
  SILENT_BEYOND,
} from './spatial';

const listener = { x: 10, y: 10 };
const overheard = (dx: number, dy = 0) => overheardMix(listener, { x: 10 + dx, y: 10 + dy });
const partner = (dx: number, dy = 0) => partnerMix(listener, { x: 10 + dx, y: 10 + dy });

describe('overheardMix', () => {
  it('plays a speaker on top of the listener at the overheard cap, centred', () => {
    expect(overheard(0)).toEqual({ gain: OVERHEARD_GAIN, pan: 0 });
  });

  it('caps an overheard voice at about a quarter of full volume', () => {
    expect(20 * Math.log10(OVERHEARD_GAIN)).toBeCloseTo(-12, 1);
    expect(overheard(0, FULL_VOLUME_WITHIN).gain).toBe(OVERHEARD_GAIN);
    expect(overheard(-1.2, 1.2).gain).toBe(OVERHEARD_GAIN);
  });

  it('gets quieter with distance in any direction', () => {
    const distances = [2, 2.5, 3, 4, 5, 6, 6.4];
    const gains = distances.map((distance) => overheard(distance).gain);

    expect(gains).toEqual([...gains].sort((a, b) => b - a));
    expect(new Set(gains).size).toBe(gains.length);
    expect(overheard(0, -3).gain).toBeCloseTo(overheard(3).gain, 12);
    expect(overheard(3, 4).gain).toBeCloseTo(overheard(-5).gain, 12);
  });

  it('is faint at the edge of earshot', () => {
    expect(overheard(5).gain).toBeGreaterThan(0);
    expect(overheard(5).gain).toBeLessThan(OVERHEARD_GAIN / 4);
  });

  it('is silent where the server stops voicing and beyond', () => {
    expect(overheard(SILENT_BEYOND).gain).toBe(0);
    expect(overheard(0, 40).gain).toBe(0);
  });

  it('pans towards the side the speaker is on', () => {
    expect(overheard(4).pan).toBeGreaterThan(0);
    expect(overheard(-4).pan).toBeCloseTo(-overheard(4).pan, 12);
    expect(overheard(0, 3).pan).toBe(0);
    expect(overheard(0, -3).pan).toBe(0);
  });

  it('pans by direction, not distance, once out of arm’s reach', () => {
    expect(overheard(3, 4).pan).toBeCloseTo(overheard(6, 8).pan, 12);
    expect(overheard(3, 4).pan).toBeLessThan(overheard(5).pan);
  });

  it('pans less for a speaker almost on top of the listener', () => {
    expect(Math.abs(overheard(0.5).pan)).toBeLessThan(Math.abs(overheard(4).pan));
  });

  it('never pans fully to one ear', () => {
    for (const dx of [-100, -3, -0.1, 0.1, 3, 100]) {
      expect(Math.abs(overheard(dx).pan)).toBeLessThan(1);
    }
  });
});

describe('partnerMix', () => {
  it('plays the player’s partner at full volume wherever they are', () => {
    for (const [dx, dy] of [[0, 0], [1, 0], [0, 3], [4, 4], [-6, 0], [0, 40]]) {
      expect(partner(dx, dy).gain).toBe(1);
    }
  });

  it('pans gently towards the side the partner is on', () => {
    expect(partner(3).pan).toBeGreaterThan(0);
    expect(partner(-3).pan).toBeCloseTo(-partner(3).pan, 12);
    expect(partner(0, 3).pan).toBe(0);
    expect(partner(100).pan).toBeLessThanOrEqual(0.3);
    expect(Math.abs(partner(3).pan)).toBeLessThan(Math.abs(overheard(3).pan));
  });
});

describe('another map', () => {
  const inside = { x: 10, y: 10, map: 'coffee_shop' };

  it('silences an overheard voice, however close its tiles', () => {
    expect(overheardMix({ ...listener, map: 'village' }, inside)).toEqual({ gain: 0, pan: 0 });
    expect(overheardMix(listener, { x: 11, y: 10 }).gain).toBe(OVERHEARD_GAIN);
    expect(overheardMix(inside, { ...inside, x: 11 }).gain).toBe(OVERHEARD_GAIN);
  });

  it('plays the partner at full volume, centred', () => {
    expect(partnerMix(listener, { ...inside, x: 14 })).toEqual({ gain: 1, pan: 0 });
  });
});

describe('on a side-view map', () => {
  let unload: () => void;
  beforeEach(() => (unload = loadStreets()));
  afterEach(() => unload());

  const lane = (x: number, y = 15): Position => ({ x, y, map: 'lychee_lane' });
  const listener = lane(45);
  const heard = (x: number, y = 15) => overheardMix(listener, lane(x, y));

  it('turns an overheard voice down by how far along the street it is, not how high', () => {
    const gains = [47, 47.5, 48, 49, 50, 51, 51.4].map((x) => heard(x).gain);

    expect(gains).toEqual([...gains].sort((a, b) => b - a));
    expect(new Set(gains).size).toBe(gains.length);
    expect(heard(45, 12).gain).toBe(OVERHEARD_GAIN);
    expect(heard(48, 12).gain).toBe(heard(48).gain);
    expect(heard(45 + SILENT_BEYOND, 12).gain).toBe(0);
  });

  it('pans by the side the speaker is on', () => {
    expect(heard(48, 12).pan).toBe(heard(48).pan);
    expect(heard(48, 12).pan).toBeCloseTo(heard(50).pan, 12);
    expect(heard(40).pan).toBeCloseTo(-heard(50).pan, 12);
    expect(heard(45, 12).pan).toBe(0);
    expect(partnerMix(listener, lane(48, 12)).pan).toBeCloseTo(partnerMix(listener, lane(50)).pan, 12);
  });

  it('silences a voice on another floor or inside a building, whatever its x', () => {
    const below = { x: 5, y: 2, map: 'coffee_shop_floor_0' };

    expect(overheardMix({ ...below, map: 'coffee_shop_floor_1' }, below)).toEqual({ gain: 0, pan: 0 });
    expect(overheardMix({ x: 30, y: 15, map: 'high_street' }, below)).toEqual({ gain: 0, pan: 0 });
    expect(partnerMix({ x: 30, y: 15, map: 'high_street' }, below)).toEqual({ gain: 1, pan: 0 });
  });
});
