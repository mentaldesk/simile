import { describe, expect, it } from 'vitest';
import { MoveThrottle } from './throttle';

describe('MoveThrottle', () => {
  it('sends the first position at once', () => {
    expect(new MoveThrottle(0.2).next({ x: 31, y: 22 }, 10)).toEqual({ x: 31, y: 22 });
  });

  it('sends at most once per interval while the position changes', () => {
    const throttle = new MoveThrottle(0.2);
    const sent = [];
    for (let frame = 0; frame < 60; frame++) {
      const position = throttle.next({ x: 31 + frame / 60, y: 22 }, frame / 60);
      if (position) sent.push(position);
    }
    expect(sent).toHaveLength(5);
  });

  it('sends nothing while the position stays the same', () => {
    const throttle = new MoveThrottle(0.2);
    throttle.next({ x: 31, y: 22 }, 0);
    expect(throttle.next({ x: 31, y: 22 }, 5)).toBeUndefined();
  });

  it('sends where the player stopped once the interval is up', () => {
    const throttle = new MoveThrottle(0.2);
    throttle.next({ x: 31, y: 22 }, 0);
    expect(throttle.next({ x: 31.5, y: 22 }, 0.1)).toBeUndefined();
    expect(throttle.next({ x: 31.5, y: 22 }, 0.2)).toEqual({ x: 31.5, y: 22 });
  });

  it('rounds to hundredths of a tile', () => {
    expect(new MoveThrottle().next({ x: 31.123456, y: 21.996 }, 0)).toEqual({ x: 31.12, y: 22 });
  });

  it('sends the same position again after forgetting', () => {
    const throttle = new MoveThrottle(0.2);
    throttle.next({ x: 31, y: 22 }, 0);
    throttle.forget();
    expect(throttle.next({ x: 31, y: 22 }, 0.05)).toEqual({ x: 31, y: 22 });
  });
});
