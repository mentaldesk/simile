import { describe, expect, it } from 'vitest';
import { dolls } from '../dolls/assets';
import { shown } from '../dolls/sprite';
import { facesLeft, PoseCache, STEPS } from './poses';

describe('the pose cache', () => {
  const figure = dolls.kofi;

  it("keeps each step of a cycle's frame, worked out once", () => {
    const cache = new PoseCache(figure);
    const first = cache.get('walking', 'east', 0.26);
    expect(cache.get('walking', 'east', 0.26 + 0.1 / STEPS)).toBe(first);
    expect(cache.get('walking', 'east', 1.26)).toBe(first);
    expect(first).toEqual(shown(figure, 'walking', 'east', Math.floor(0.26 * STEPS) / STEPS));
    expect(cache.get('walking', 'east', 0.5)).not.toBe(first);
    expect(cache.size).toBe(2);
  });

  it('mirrors the westward facings and shares the rest', () => {
    const cache = new PoseCache(figure);
    expect(facesLeft('north_west')).toBe(true);
    expect(facesLeft('east')).toBe(false);
    expect(cache.get('walking', 'west', 0.1).flip).toBe(true);
    expect(cache.get('walking', 'east', 0.1).flip).toBe(false);
    expect(cache.get('standing', 'south', 0)).toBe(cache.get('standing', 'east', 0));
    expect(cache.get('standing', 'north', 0)).toBe(cache.get('looking', 'south_east', 0));
  });

  it('sits at a desk, climbs a ladder from behind and takes stairs walking', () => {
    const cache = new PoseCache(figure);
    expect(cache.get('working', 'north', 0, true).frame).toBe(figure.poses.sit[0]);
    expect(cache.get('working', 'north', 0).frame).toBe(figure.poses.stand[0]);
    expect(cache.get('climbing', 'north', 0, false, 'ladder').frame).toBe(figure.poses.climb[0]);
    expect(figure.poses.walk).toContain(cache.get('climbing', 'east', 0.1, false, 'stairs').frame);
  });

  it('runs once a walk is more than half a run', () => {
    const cache = new PoseCache(figure);
    expect(figure.poses.walk).toContain(cache.get('walking', 'east', 0.1, false, undefined, 0.4).frame);
    expect(figure.poses.run).toContain(cache.get('walking', 'east', 0.1, false, undefined, 0.6).frame);
    expect(cache.get('standing', 'east', 0, false, undefined, 1)).toBe(cache.get('standing', 'east', 0));
  });
});
