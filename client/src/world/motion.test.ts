import { describe, expect, it } from 'vitest';
import { Mover } from './motion';
import { IDLE_AFTER_SECONDS, WALKING_SPEED } from './tuning';

const FRAME = 1 / 60;

function run(mover: Mover, seconds: number): void {
  for (let t = 0; t < seconds - 1e-9; t += FRAME) mover.update(FRAME);
}

describe('Mover', () => {
  it('walks to the next tile at walking speed', () => {
    const mover = new Mover({ x: 4, y: 6 });
    mover.moveTo({ x: 5, y: 6 });

    run(mover, 0.5);
    expect(mover.position.x).toBeCloseTo(4 + 0.5 * WALKING_SPEED, 5);
    expect(mover.position.y).toBe(6);
    expect(mover.walking).toBe(true);

    run(mover, 1 / WALKING_SPEED);
    expect(mover.position).toEqual({ x: 5, y: 6 });
  });

  it('walks a diagonal step over its length', () => {
    const mover = new Mover({ x: 4, y: 6 });
    mover.moveTo({ x: 5, y: 5 });

    run(mover, 1 / WALKING_SPEED);
    expect(mover.position.x).toBeLessThan(5);

    run(mover, (Math.SQRT2 - 1) / WALKING_SPEED + FRAME);
    expect(mover.position).toEqual({ x: 5, y: 5 });
  });

  it('follows each tile in turn rather than cutting corners', () => {
    const mover = new Mover({ x: 0, y: 0 });
    mover.moveTo({ x: 1, y: 0 });
    mover.moveTo({ x: 1, y: 1 });

    run(mover, 0.5);
    expect(mover.position.y).toBe(0);
    run(mover, 1);
    expect(mover.position.x).toBe(1);
  });

  it('walks continuously when each tile arrives as it reaches the last', () => {
    const mover = new Mover({ x: 0, y: 0 });
    for (let x = 1; x <= 5; x++) {
      mover.moveTo({ x, y: 0 });
      for (let t = 0; t < 1 / WALKING_SPEED; t += FRAME) {
        mover.update(FRAME);
        expect(mover.walking).toBe(true);
      }
    }
  });

  it('stops walking soon after it arrives', () => {
    const mover = new Mover({ x: 0, y: 0 });
    mover.moveTo({ x: 1, y: 0 });
    run(mover, 1 / WALKING_SPEED + FRAME);
    expect(mover.walking).toBe(true);
    run(mover, IDLE_AFTER_SECONDS + FRAME);
    expect(mover.walking).toBe(false);
  });

  it('snaps to a position more than a step and a half away', () => {
    const mover = new Mover({ x: 0, y: 0 });
    mover.moveTo({ x: 1, y: 0 });
    mover.moveTo({ x: 9, y: 4 });

    expect(mover.position).toEqual({ x: 9, y: 4 });
    run(mover, 1);
    expect(mover.position).toEqual({ x: 9, y: 4 });
    expect(mover.walking).toBe(false);
  });

  it('hurries when it falls behind', () => {
    const mover = new Mover({ x: 0, y: 0 });
    for (let x = 1; x <= 4; x++) mover.moveTo({ x, y: 0 });

    run(mover, 1);
    expect(mover.position.x).toBeGreaterThan(1.5 * WALKING_SPEED);
  });

  it('snaps when it falls far behind', () => {
    const mover = new Mover({ x: 0, y: 0 });
    for (let x = 1; x <= 10; x++) mover.moveTo({ x, y: 0 });

    mover.update(FRAME);
    expect(mover.position).toEqual({ x: 10, y: 0 });
  });

  it('ignores a move to where it already is', () => {
    const mover = new Mover({ x: 3, y: 3 });
    mover.moveTo({ x: 3, y: 3 });
    mover.update(FRAME);
    expect(mover.walking).toBe(false);
  });
});
