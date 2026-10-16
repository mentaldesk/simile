import { describe, expect, it } from 'vitest';
import { feetOf, project, unproject } from './projection';

const TILE = { width: 96, height: 48, px_per_metre_up: 53.443 };

describe('project', () => {
  it('puts grid north up and to the right, and grid east down and to the right', () => {
    expect(project(TILE, { x: 0, y: 0 })).toEqual({ x: 0, y: 0 });
    expect(project(TILE, { x: 0, y: -1 })).toEqual({ x: 48, y: -24 });
    expect(project(TILE, { x: 1, y: 0 })).toEqual({ x: 48, y: 24 });
    expect(project(TILE, { x: 0, y: 1 })).toEqual({ x: -48, y: 24 });
    expect(project(TILE, { x: 64, y: 42 })).toEqual({ x: 1056, y: 2544 });
  });

  it('draws a point higher by its height in metres', () => {
    expect(project(TILE, { x: 3, y: 2 }, 0.18).y).toBeCloseTo(120 - 9.62, 2);
    expect(project(TILE, { x: 3, y: 2 }, -0.08).y).toBeCloseTo(120 + 4.28, 2);
  });
});

describe('unproject', () => {
  it('finds the ground point under a screen point', () => {
    for (const point of [
      { x: 0, y: 0 },
      { x: 12.5, y: 3.25 },
      { x: 63, y: 41 },
    ]) {
      const back = unproject(TILE, project(TILE, point));
      expect(back.x).toBeCloseTo(point.x);
      expect(back.y).toBeCloseTo(point.y);
    }
  });
});

describe('feetOf', () => {
  it('stands an entity in the middle of its tile', () => {
    expect(feetOf({ x: 4, y: 6 })).toEqual({ x: 4.5, y: 6.5 });
    expect(project(TILE, feetOf({ x: 0, y: 0 }))).toEqual({ x: 0, y: 24 });
  });
});
