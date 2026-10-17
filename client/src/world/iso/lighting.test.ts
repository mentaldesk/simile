import { describe, expect, it } from 'vitest';
import {
  LightMap,
  residentLight,
  tintColour,
  type LightMapInfo,
  type Rgb,
  type SetLight,
} from './lighting';
import type { SceneryManifest } from './manifest';
import type { CharacterManifest } from './sheets';

const scenery = import.meta.glob<SceneryManifest>('../../../../content/art/iso/scenery/*.json', {
  eager: true,
  import: 'default',
});
const { sets } = Object.values(
  import.meta.glob<CharacterManifest>('../../../../content/art/iso/characters/characters.json', {
    eager: true,
    import: 'default',
  }),
)[0];

const INFO: LightMapInfo = {
  image: 'light.webp',
  px_per_tile: 8,
  width: 4 * 8,
  height: 3 * 8,
  sun_y: 3 * 8,
  scale: 2,
};

type Spot = { tint: Rgb; sun: number };

/** A 4 × 3 tile map, open everywhere except the given tiles. */
function lightMap(spots: Record<string, Spot> = {}, info = INFO): LightMap {
  const rgba = new Uint8ClampedArray(info.width * (info.sun_y + info.height) * 4);
  for (let v = 0; v < info.height; v++) {
    for (let u = 0; u < info.width; u++) {
      const tile = `${Math.floor(u / info.px_per_tile)},${Math.floor(v / info.px_per_tile)}`;
      const { tint, sun } = spots[tile] ?? { tint: [1, 1, 1], sun: 1 };
      const [top, bottom] = [v * info.width + u, (info.sun_y + v) * info.width + u].map((i) => i * 4);
      tint.forEach((channel, i) => (rgba[top + i] = Math.round((channel / info.scale) * 255)));
      rgba.fill(Math.round(sun * 255), bottom, bottom + 3);
      rgba[top + 3] = rgba[bottom + 3] = 255;
    }
  }
  return new LightMap(info, rgba);
}

const LAMP: Spot = { tint: [2, 1.6, 1], sun: 0.2 };
const SHADE: Spot = { tint: [0.5, 0.5, 0.6], sun: 0 };

const set = (tint: Rgb, strength: number): SetLight => ({
  sun: { azimuth: 0, elevation: 45 },
  tint,
  shadow: { strength, direction: [0, -1], length: 1, tip: [0, 0] },
});

describe('LightMap', () => {
  const map = lightMap({ '1,1': LAMP, '2,0': SHADE });

  it('reads the tint above and the sun below, at the feet', () => {
    expect(map.tintAt({ x: 1.5, y: 1.5 })).toEqual([2, 1.6, 1].map((c) => expect.closeTo(c, 2)));
    expect(map.sunAt({ x: 1.5, y: 1.5 })).toBeCloseTo(0.2, 2);
    expect(map.tintAt({ x: 2.2, y: 0.9 })).toEqual([0.5, 0.5, 0.6].map((c) => expect.closeTo(c, 2)));
    expect(map.sunAt({ x: 2.2, y: 0.9 })).toBe(0);
    expect(map.tintAt({ x: 0.5, y: 2.5 })).toEqual([1, 1, 1].map((c) => expect.closeTo(c, 2)));
    expect(map.sunAt({ x: 0.5, y: 2.5 })).toBe(1);
  });

  it('samples the light map pixel under the feet, px_per_tile to a tile', () => {
    expect(map.sunAt({ x: 2.999, y: 0.5 })).toBe(0);
    expect(map.sunAt({ x: 3.001, y: 0.5 })).toBe(1);
    expect(map.sunAt({ x: 1.999, y: 0.999 })).toBe(1);
  });

  it('holds the edge for feet off the map', () => {
    expect(map.sunAt({ x: 2.5, y: -1 })).toBe(0);
    expect(map.sunAt({ x: 9, y: 9 })).toBe(1);
  });

  it('has a tint and a sun half for each tile of every manifest', () => {
    for (const { map: size, light_map } of Object.values(scenery)) {
      expect(light_map.width).toBe(size.width * light_map.px_per_tile);
      expect(light_map.height).toBe(size.height * light_map.px_per_tile);
      expect(light_map.sun_y).toBe(light_map.height);
      expect(light_map.scale).toBeGreaterThanOrEqual(1);
    }
  });
});

describe('residentLight', () => {
  const map = lightMap({ '1,1': LAMP, '2,0': SHADE });
  const open = { x: 0.5, y: 0.5 };
  const lamp = { x: 1.5, y: 1.5 };
  const shade = { x: 2.5, y: 0.5 };

  it("is the set's tint and shadow strength in the open", () => {
    const light = residentLight([{ weight: 1, light: sets.afternoon, lightMap: map }], open);
    expect(light.tint).toEqual(sets.afternoon.tint.map((c) => expect.closeTo(c, 2)));
    expect(light.shadows).toEqual([expect.closeTo(sets.afternoon.shadow.strength, 5)]);
  });

  it('multiplies the tint by the light map, scaled down to keep its hue', () => {
    const night = set([0.2, 0.3, 0.4], 0.6);
    const { tint } = residentLight([{ weight: 1, light: night, lightMap: map }], lamp);
    expect(tint).toEqual([0.4, 0.48, 0.4].map((c) => expect.closeTo(c, 2)));

    const bright = set([0.8, 0.9, 1], 0.6);
    const over = residentLight([{ weight: 1, light: bright, lightMap: map }], lamp).tint;
    expect(Math.max(...over)).toBeCloseTo(1, 5);
    expect(over[0] / over[1]).toBeCloseTo((0.8 * 2) / (0.9 * 1.6), 2);
    expect(over[2] / over[1]).toBeCloseTo(1 / (0.9 * 1.6), 2);
  });

  it('takes the drop shadow away where the sun is blocked', () => {
    const lit = [{ weight: 1, light: set([1, 1, 1], 0.6), lightMap: map }];
    expect(residentLight(lit, shade).shadows).toEqual([0]);
    expect(residentLight(lit, lamp).shadows[0]).toBeCloseTo(0.6 * 0.2, 2);
  });

  it("lights each set by its own light map before blending the tints by weight", () => {
    const shaded = lightMap({ '0,0': SHADE });
    const evening = set([1, 0.5, 0.4], 0.6);
    const night = set([0.2, 0.3, 0.4], 0.7);
    const layers = [
      { weight: 0.75, light: evening, lightMap: shaded },
      { weight: 0.25, light: night, lightMap: map },
    ];
    const light = residentLight(layers, open);
    const wanted = [0.75 * 0.5 + 0.25 * 0.2, 0.75 * 0.25 + 0.25 * 0.3, 0.75 * 0.24 + 0.25 * 0.4];
    expect(light.tint).toEqual(wanted.map((c) => expect.closeTo(c, 2)));
    expect(light.shadows).toEqual([0, expect.closeTo(0.25 * 0.7, 2)]);
  });

  it('keeps both shadows at their own strength times their weight through a fade', () => {
    for (const weight of [0, 0.3, 0.5, 1]) {
      const layers = [
        { weight: 1 - weight, light: sets.afternoon, lightMap: map },
        { weight, light: sets.evening, lightMap: map },
      ];
      const { shadows } = residentLight(layers, open);
      expect(shadows[0]).toBeCloseTo(sets.afternoon.shadow.strength * (1 - weight), 2);
      expect(shadows[1]).toBeCloseTo(sets.evening.shadow.strength * weight, 2);
    }
  });
});

describe('tintColour', () => {
  it("packs a tint for Phaser's setTint", () => {
    expect(tintColour([1, 1, 1])).toBe(0xffffff);
    expect(tintColour([1, 0.5, 0])).toBe(0xff8000);
    expect(tintColour([1.2, -0.1, 0.2])).toBe(0xff0033);
  });
});
