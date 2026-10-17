import { describe, expect, it } from 'vitest';
import { isoZoom, nativeCanvas } from './canvas';
import { MAX_TILES_ACROSS } from './tuning';

const TILE = { width: 96, height: 48, px_per_metre_up: 53.443 };

const window = (innerWidth: number, innerHeight: number, devicePixelRatio: number) => ({
  innerWidth,
  innerHeight,
  devicePixelRatio,
});

describe('nativeCanvas', () => {
  it('sizes the canvas in device pixels and shows it at the window size', () => {
    expect(nativeCanvas(window(1440, 900, 2))).toEqual({ width: 2880, height: 1800, zoom: 0.5 });
    expect(nativeCanvas(window(1920, 1080, 1))).toEqual({ width: 1920, height: 1080, zoom: 1 });
  });

  it('rounds down to whole device pixels, but keeps at least one', () => {
    const { width, height } = nativeCanvas(window(1013, 677, 1.25));
    expect({ width, height }).toEqual({ width: 1266, height: 846 });
    expect(nativeCanvas(window(0, 0, 2))).toMatchObject({ width: 1, height: 1 });
  });
});

describe('isoZoom', () => {
  const tilesAcross = (cssWidth: number, devicePixelRatio: number) => {
    const { width } = nativeCanvas(window(cssWidth, 800, devicePixelRatio));
    return width / isoZoom(width, devicePixelRatio, TILE) / TILE.width;
  };

  it('draws one art pixel per CSS pixel, so a bigger window shows more', () => {
    expect(isoZoom(1280, 1, TILE)).toBe(1);
    expect(isoZoom(2880, 2, TILE)).toBe(2);
    expect(tilesAcross(1280, 1)).toBeCloseTo(13.3, 1);
    expect(tilesAcross(1440, 2)).toBe(15);
    expect(tilesAcross(1920, 1)).toBe(MAX_TILES_ACROSS);
    expect(tilesAcross(1920, 2)).toBe(MAX_TILES_ACROSS);
  });

  it('keeps one art pixel per CSS pixel on a 1x window up to 1.5 times the cap', () => {
    expect(isoZoom(2560, 1, TILE)).toBe(1);
    expect(tilesAcross(2560, 1)).toBeCloseTo(26.7, 1);
    expect(isoZoom(2879, 1, TILE)).toBe(1);
  });

  it('scales up in whole steps past that, so the view stays 15 to 30 tiles across', () => {
    expect(isoZoom(2880, 1, TILE)).toBe(2);
    expect(isoZoom(3840, 1, TILE)).toBe(2);
    expect(isoZoom(4800, 1, TILE)).toBe(3);
    expect(isoZoom(5120, 2, TILE)).toBe(3);
    for (const cssWidth of [1921, 2560, 2879, 2880, 3840, 4799, 5120]) {
      for (const ratio of [1, 2]) {
        expect(tilesAcross(cssWidth, ratio)).toBeGreaterThanOrEqual(MAX_TILES_ACROSS * 0.75);
        expect(tilesAcross(cssWidth, ratio)).toBeLessThanOrEqual(MAX_TILES_ACROSS * 1.5);
      }
    }
  });

  it('keeps art pixels whole device pixels at fractional pixel ratios', () => {
    expect(isoZoom(1500, 1.5, TILE)).toBe(2);
    expect(isoZoom(1250, 1.25, TILE)).toBe(1);
  });

  it('never goes below one device pixel per art pixel', () => {
    expect(isoZoom(0, 1, TILE)).toBe(1);
    expect(isoZoom(300, 0.5, TILE)).toBe(1);
  });
});
