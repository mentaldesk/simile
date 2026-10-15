import { describe, expect, it } from 'vitest';
import { feetOf, followScroll, pixelZoom, toCanvas } from './view';

const VIEW = { width: 640, height: 360 };
const WORLD = { width: 1024, height: 672 };
const ZOOM = 3;

describe('feetOf', () => {
  it('puts the feet on the bottom centre of the tile', () => {
    expect(feetOf({ x: 4, y: 6 })).toEqual({ x: 72, y: 112 });
  });

  it('rounds to whole world pixels mid-step', () => {
    expect(feetOf({ x: 4.52, y: 6.01 })).toEqual({ x: 80, y: 112 });
  });
});

describe('followScroll', () => {
  it('centres the view on the target', () => {
    const scroll = followScroll({ x: 500, y: 300 }, VIEW, WORLD, ZOOM);
    expect(toCanvas({ x: 500, y: 300 }, scroll, VIEW, ZOOM)).toEqual({ x: 320, y: 180 });
  });

  it('keeps every art pixel on whole canvas pixels', () => {
    for (const target of [{ x: 500.4, y: 300.6 }, { x: 0, y: 0 }, { x: 1024, y: 672 }]) {
      const scroll = followScroll(target, VIEW, WORLD, ZOOM);
      const corner = toCanvas({ x: 17, y: 23 }, scroll, VIEW, ZOOM);
      expect(Number.isInteger(corner.x) && Number.isInteger(corner.y)).toBe(true);
    }
  });

  it('stops at the edges of the world', () => {
    const topLeft = followScroll({ x: 0, y: 0 }, VIEW, WORLD, ZOOM);
    const origin = toCanvas({ x: 0, y: 0 }, topLeft, VIEW, ZOOM);
    expect(origin.x).toBeLessThanOrEqual(0);
    expect(origin.x).toBeGreaterThan(-ZOOM);
    expect(origin.y).toBeLessThanOrEqual(0);
    expect(origin.y).toBeGreaterThan(-ZOOM);

    const bottomRight = followScroll({ x: 2000, y: 2000 }, VIEW, WORLD, ZOOM);
    const end = toCanvas({ x: WORLD.width, y: WORLD.height }, bottomRight, VIEW, ZOOM);
    expect(end.x).toBeGreaterThanOrEqual(VIEW.width);
    expect(end.x).toBeLessThan(VIEW.width + ZOOM);
    expect(end.y).toBeGreaterThanOrEqual(VIEW.height);
    expect(end.y).toBeLessThan(VIEW.height + ZOOM);
  });

  it('centres a world smaller than the view', () => {
    const scroll = followScroll({ x: 0, y: 0 }, VIEW, { width: 100, height: 60 }, ZOOM);
    expect(toCanvas({ x: 50, y: 30 }, scroll, VIEW, ZOOM)).toEqual({ x: 320, y: 180 });
  });
});

describe('pixelZoom', () => {
  it('picks the largest whole multiple that fits', () => {
    expect(pixelZoom({ width: 1024, height: 768 }, VIEW)).toBe(1);
    expect(pixelZoom({ width: 1280, height: 720 }, VIEW)).toBe(2);
    expect(pixelZoom({ width: 1919, height: 1200 }, VIEW)).toBe(2);
    expect(pixelZoom({ width: 2560, height: 1100 }, VIEW)).toBe(3);
  });

  it('never goes below 1, however small the window', () => {
    expect(pixelZoom({ width: 500, height: 300 }, VIEW)).toBe(1);
    expect(pixelZoom({ width: 0, height: 0 }, VIEW)).toBe(1);
  });

  it('counts device pixels on high-density screens', () => {
    expect(pixelZoom({ width: 1024, height: 768 }, VIEW, 2)).toBe(1.5);
    expect(pixelZoom({ width: 1440, height: 900 }, VIEW, 2)).toBe(2);
    expect(pixelZoom({ width: 1280, height: 720 }, VIEW, 1.5)).toBe(2);
  });
});
