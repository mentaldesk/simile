import type { Point } from '../view';

export type Rgb = [r: number, g: number, b: number];

/** A set's constants for characters: `sets.<set>` in `characters.json`. */
export type SetLight = {
  sun: { azimuth: number; elevation: number };
  tint: Rgb;
  shadow: {
    strength: number;
    direction: [x: number, y: number];
    length: number;
    tip: [x: number, y: number];
  };
};

/** `light_map` in a scenery manifest. */
export type LightMapInfo = {
  image: string;
  px_per_tile: number;
  width: number;
  height: number;
  sun_y: number;
  scale: number;
};

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max);

export class LightMap {
  private readonly info: LightMapInfo;
  private readonly rgba: Uint8ClampedArray;

  constructor(info: LightMapInfo, rgba: Uint8ClampedArray) {
    this.info = info;
    this.rgba = rgba;
  }

  tintAt(feet: Point): Rgb {
    const i = this.index(feet, 0);
    const k = this.info.scale / 255;
    return [this.rgba[i] * k, this.rgba[i + 1] * k, this.rgba[i + 2] * k];
  }

  sunAt(feet: Point): number {
    return this.rgba[this.index(feet, this.info.sun_y)] / 255;
  }

  private index({ x, y }: Point, top: number): number {
    const { px_per_tile, width, height } = this.info;
    const u = clamp(Math.floor(x * px_per_tile), 0, width - 1);
    const v = clamp(Math.floor(y * px_per_tile), 0, height - 1);
    return ((top + v) * width + u) * 4;
  }
}

export type LitLayer = { weight: number; light: SetLight; lightMap: LightMap };

export type ResidentLight = { tint: Rgb; shadows: number[] };

export function residentLight(layers: readonly LitLayer[], feet: Point): ResidentLight {
  const tint: Rgb = [0, 0, 0];
  const shadows = layers.map(({ weight, light, lightMap }) => {
    const here = lightMap.tintAt(feet);
    const lit = light.tint.map((channel, i) => channel * here[i]);
    const over = Math.max(1, ...lit);
    lit.forEach((channel, i) => (tint[i] += (weight * channel) / over));
    return light.shadow.strength * lightMap.sunAt(feet) * weight;
  });
  return { tint, shadows };
}

const byte = (channel: number) => Math.round(clamp(channel, 0, 1) * 255);

export const tintColour = ([r, g, b]: Rgb): number => (byte(r) << 16) | (byte(g) << 8) | byte(b);
