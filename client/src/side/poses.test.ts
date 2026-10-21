import { describe, expect, it } from 'vitest';
import { dolls } from '../dolls/assets';
import { posed } from '../dolls/rig';
import { facesLeft, PoseCache, RUN_STEPS, STEPS } from './poses';

describe('the pose cache', () => {
  const doll = dolls.kofi;

  it("keeps the rig's pose for each step of a cycle, worked out once", () => {
    const cache = new PoseCache(doll);
    const first = cache.get('walking', 'east', 0.26);
    expect(cache.get('walking', 'east', 0.26 + 0.1 / STEPS)).toBe(first);
    expect(cache.get('walking', 'east', 1.26)).toBe(first);
    expect(first).toEqual(posed(doll, 'walking', 'east', Math.floor(0.26 * STEPS) / STEPS));
    expect(cache.get('walking', 'east', 0.5)).not.toBe(first);
    expect(cache.size).toBe(2);
  });

  it('shares a pose between the side facings, mirrored by the caller', () => {
    const cache = new PoseCache(doll);
    expect(cache.get('standing', 'west', 0)).toBe(cache.get('standing', 'south_east', 0));
    expect(facesLeft('north_west')).toBe(true);
    expect(facesLeft('east')).toBe(false);
    expect(cache.get('standing', 'north', 0).view).toBe('back');
    expect(cache.get('standing', 'south', 0).view).toBe('front');
  });

  it('keeps seated and climbing variants apart', () => {
    const cache = new PoseCache(doll);
    expect(cache.get('working', 'north', 0, true)).toEqual(posed(doll, 'working', 'north', 0, { seated: true }));
    expect(cache.get('working', 'north', 0, true)).not.toEqual(cache.get('working', 'north', 0));
    expect(cache.get('climbing', 'east', 0, false, 'ladder')).toEqual(
      posed(doll, 'climbing', 'east', 0, { on: 'ladder' }),
    );
  });

  it('keeps a pose for each step from a walk to a run, and only for walking', () => {
    const cache = new PoseCache(doll);
    expect(cache.get('walking', 'east', 0.25, false, undefined, 0)).toBe(cache.get('walking', 'east', 0.25));
    expect(cache.get('walking', 'east', 0.25, false, undefined, 0.4 / RUN_STEPS)).toBe(cache.get('walking', 'east', 0.25));
    expect(cache.get('walking', 'east', 0.25, false, undefined, 1)).toEqual(posed(doll, 'walking', 'east', 0.25, { run: 1 }));
    expect(cache.get('walking', 'south', 0.25, false, undefined, 0.5)).toEqual(
      posed(doll, 'walking', 'south', 0.25, { run: Math.round(0.5 * RUN_STEPS) / RUN_STEPS }),
    );
    expect(cache.get('standing', 'east', 0, false, undefined, 1)).toBe(cache.get('standing', 'east', 0));
  });
});
