import { describe, expect, it } from 'vitest';
import { CritterLight } from './critter-light';
import {
  LightMap,
  residentLight,
  tintColour,
  type LightMapInfo,
  type LitLayer,
  type Rgb,
  type SetLight,
} from './lighting';

const [WIDTH, HEIGHT, PX] = [4, 3, 8];
const INFO: LightMapInfo = {
  image: 'light.webp',
  px_per_tile: PX,
  width: WIDTH * PX,
  height: HEIGHT * PX,
  sun_y: HEIGHT * PX,
  scale: 2,
};

/** Each tile its own tint, from `tints` by tile, white where it's missing. */
function lightMap(tints: Record<string, Rgb>): LightMap {
  const rgba = new Uint8ClampedArray(INFO.width * (INFO.sun_y + INFO.height) * 4).fill(255);
  for (let v = 0; v < INFO.height; v++) {
    for (let u = 0; u < INFO.width; u++) {
      const tint = tints[`${Math.floor(u / PX)},${Math.floor(v / PX)}`] ?? [1, 1, 1];
      tint.forEach((channel, i) => (rgba[(v * INFO.width + u) * 4 + i] = Math.round((channel / INFO.scale) * 255)));
    }
  }
  return new LightMap(INFO, rgba);
}

const set = (tint: Rgb): SetLight => ({
  sun: { azimuth: 0, elevation: 45 },
  tint,
  shadow: { strength: 0.5, direction: [0, -1], length: 1, tip: [0, 0] },
});

const day = lightMap({ '1,1': [1.8, 1.4, 0.9], '2,1': [0.4, 0.5, 0.7], '0,2': [1.2, 1, 1] });
const dusk = lightMap({ '1,1': [0.6, 0.6, 1.1], '3,0': [1.9, 1.2, 0.6] });
const lit: LitLayer[] = [
  { weight: 0.3, light: set([0.9, 0.85, 0.8]), lightMap: day },
  { weight: 0.7, light: set([0.35, 0.4, 0.6]), lightMap: dusk },
];

describe('CritterLight', () => {
  it('lights a critter in the middle of a tile as a resident there', () => {
    const light = new CritterLight(WIDTH, HEIGHT);
    for (let y = 0; y < HEIGHT; y++) {
      for (let x = 0; x < WIDTH; x++) {
        const at = { x: x + 0.5, y: y + 0.5 };
        expect(light.colourAt(lit, at)).toBe(tintColour(residentLight(lit, at).tint));
        expect(light.colourAt([lit[0]], at)).toBe(tintColour(residentLight([lit[0]], at).tint));
      }
    }
  });

  it('blends between the tiles, and holds at the edges', () => {
    const light = new CritterLight(WIDTH, HEIGHT);
    const red = (at: { x: number; y: number }) => light.colourAt([lit[0]], at) >> 16;
    const [here, there] = [red({ x: 1.5, y: 1.5 }), red({ x: 2.5, y: 1.5 })];
    const between = red({ x: 2, y: 1.5 });
    expect(between).toBeLessThan(Math.max(here, there));
    expect(between).toBeGreaterThan(Math.min(here, there));
    expect(red({ x: -3, y: 0.2 })).toBe(red({ x: 0.5, y: 0.5 }));
    expect(red({ x: 9, y: 9 })).toBe(red({ x: WIDTH - 0.5, y: HEIGHT - 0.5 }));
  });
});
