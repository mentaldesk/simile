import type { Point } from '../view';
import { GROUND_DEPTH } from './depth';
import type { SetLight } from './lighting';
import type { IsoTile } from './manifest';
import { project, unproject } from './projection';

/** On the ground, under every object and resident. */
export const SHADOW_DEPTH = GROUND_DEPTH + 1;

export const CONTACT_ALPHA = 0.35;

/** About 0.4 m wide, a tile being 1.1 m. */
const HALF_WIDTH_TILES = 0.2 / 1.1;
const CONTACT = { along: 0.3, across: 0.26, blur: 1.5 };
const SUPERSAMPLE = 4;
const OUTLINE_POINTS = 48;

/** A soft shape on screen: `alpha` is `width` × `height` bytes, with the feet at `origin`. */
export type ShadowMask = { width: number; height: number; origin: Point; alpha: Uint8ClampedArray };

/** In tiles from the feet: `axis` is a unit step on the map, with radii along and across it. */
type Ellipse = { centre: Point; axis: Point; along: number; across: number };

/** From the feet away from the sun, as `drop_shadow` in `docs/style-study/compose.py`. */
export function dropShadow(shadow: SetLight['shadow'], tile: IsoTile): ShadowMask {
  const { direction: [x, y], length } = shadow;
  const ellipse = {
    centre: { x: (x * length) / 2, y: (y * length) / 2 },
    axis: { x, y },
    along: length / 2 + HALF_WIDTH_TILES,
    across: HALF_WIDTH_TILES,
  };
  return rasterise(ellipse, Math.min(1 + length * 0.4, 5), tile);
}

/** Under the feet, the same in every set: wider across the screen than up it. */
export function contactShadow(tile: IsoTile): ShadowMask {
  const ellipse = {
    centre: { x: 0, y: 0 },
    axis: { x: Math.SQRT1_2, y: -Math.SQRT1_2 },
    along: CONTACT.along,
    across: CONTACT.across,
  };
  return rasterise(ellipse, CONTACT.blur, tile);
}

function inside({ centre, axis, along, across }: Ellipse, { x, y }: Point): boolean {
  const [dx, dy] = [x - centre.x, y - centre.y];
  const u = (dx * axis.x + dy * axis.y) / along;
  const v = (dy * axis.x - dx * axis.y) / across;
  return u * u + v * v <= 1;
}

function rasterise(ellipse: Ellipse, blur: number, tile: IsoTile): ShadowMask {
  const { centre, axis, along, across } = ellipse;
  const outline = Array.from({ length: OUTLINE_POINTS }, (_, i) => {
    const a = (2 * Math.PI * i) / OUTLINE_POINTS;
    const [u, v] = [along * Math.cos(a), across * Math.sin(a)];
    const [x, y] = [centre.x + u * axis.x - v * axis.y, centre.y + u * axis.y + v * axis.x];
    return project(tile, { x, y });
  });
  const pad = Math.ceil(blur * 3) + 2;
  const x0 = Math.floor(Math.min(...outline.map(({ x }) => x))) - pad;
  const y0 = Math.floor(Math.min(...outline.map(({ y }) => y))) - pad;
  const width = Math.ceil(Math.max(...outline.map(({ x }) => x))) + pad - x0;
  const height = Math.ceil(Math.max(...outline.map(({ y }) => y))) + pad - y0;
  const cover = new Float32Array(width * height);
  const step = 1 / SUPERSAMPLE;
  for (let j = 0; j < height; j++) {
    for (let i = 0; i < width; i++) {
      let hits = 0;
      for (let b = 0; b < SUPERSAMPLE; b++) {
        for (let a = 0; a < SUPERSAMPLE; a++) {
          const screen = { x: x0 + i + (a + 0.5) * step, y: y0 + j + (b + 0.5) * step };
          if (inside(ellipse, unproject(tile, screen))) hits++;
        }
      }
      cover[j * width + i] = hits * step * step;
    }
  }
  const blurred = gaussianBlur(cover, width, height, blur);
  return {
    width,
    height,
    origin: { x: -x0, y: -y0 },
    alpha: Uint8ClampedArray.from(blurred, (value) => Math.round(value * 255)),
  };
}

function gaussianBlur(values: Float32Array, width: number, height: number, sigma: number): Float32Array {
  const radius = Math.ceil(sigma * 3);
  const kernel = Array.from({ length: 2 * radius + 1 }, (_, i) =>
    Math.exp(-((i - radius) ** 2) / (2 * sigma * sigma)),
  );
  const total = kernel.reduce((sum, weight) => sum + weight, 0);
  const pass = (source: Float32Array, dx: number, dy: number) => {
    const out = new Float32Array(source.length);
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        let sum = 0;
        for (let k = -radius; k <= radius; k++) {
          const [sx, sy] = [x + k * dx, y + k * dy];
          if (sx < 0 || sx >= width || sy < 0 || sy >= height) continue;
          sum += source[sy * width + sx] * kernel[k + radius];
        }
        out[y * width + x] = sum / total;
      }
    }
    return out;
  };
  return pass(pass(values, 1, 0), 0, 1);
}
