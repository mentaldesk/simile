import { describe, expect, it } from 'vitest';
import { MoveThrottle } from './throttle';

const at = (x: number, y: number, map = 'high_street') => ({ x, y, map });

describe('MoveThrottle', () => {
  it('sends the first position at once', () => {
    expect(new MoveThrottle(0.2).next(at(31, 15), 10)).toEqual(at(31, 15));
  });

  it('sends at most once per interval while the position changes', () => {
    const throttle = new MoveThrottle(0.2);
    const sent = [];
    for (let frame = 0; frame < 60; frame++) {
      const position = throttle.next(at(31 + frame / 60, 15), frame / 60);
      if (position) sent.push(position);
    }
    expect(sent).toHaveLength(5);
  });

  it('sends nothing while the position stays the same', () => {
    const throttle = new MoveThrottle(0.2);
    throttle.next(at(31, 15), 0);
    expect(throttle.next(at(31, 15), 5)).toBeUndefined();
  });

  it('sends where the player stopped once the interval is up', () => {
    const throttle = new MoveThrottle(0.2);
    throttle.next(at(31, 15), 0);
    expect(throttle.next(at(31.5, 15), 0.1)).toBeUndefined();
    expect(throttle.next(at(31.5, 15), 0.2)).toEqual(at(31.5, 15));
  });

  it('rounds to hundredths of a tile', () => {
    expect(new MoveThrottle().next(at(31.123456, 14.996), 0)).toEqual(at(31.12, 15));
  });

  it('sends the same position again after forgetting', () => {
    const throttle = new MoveThrottle(0.2);
    throttle.next(at(31, 15), 0);
    throttle.forget();
    expect(throttle.next(at(31, 15), 0.05)).toEqual(at(31, 15));
  });

  it('sends a move onto another map at once, with its map', () => {
    const throttle = new MoveThrottle(0.2);
    throttle.next(at(43, 15), 0);
    expect(throttle.next(at(18, 2, 'coffee_shop_floor_0'), 0.05)).toEqual(at(18, 2, 'coffee_shop_floor_0'));
    expect(throttle.next(at(17.9, 2, 'coffee_shop_floor_0'), 0.1)).toBeUndefined();
  });

  it('sends a move back to the same tile on another map', () => {
    const throttle = new MoveThrottle(0.2);
    throttle.next(at(5, 2, 'coffee_shop_floor_0'), 0);
    expect(throttle.next(at(5, 2, 'coffee_shop_floor_1'), 0.01)).toEqual(at(5, 2, 'coffee_shop_floor_1'));
  });
});
