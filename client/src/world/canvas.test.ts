import { describe, expect, it } from 'vitest';
import { nativeCanvas } from './canvas';

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
