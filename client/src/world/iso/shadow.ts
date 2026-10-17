import type { Point } from '../view';
import { GROUND_DEPTH } from './depth';
import type { SetLight } from './lighting';
import type { IsoTile } from './manifest';
import { project, unproject } from './projection';

export const SHADOW_DEPTH = GROUND_DEPTH + 1;

export const CONTACT_ALPHA = 0.35;

/** About 0.4 m wide, a tile being 1.1 m. */
const HALF_WIDTH_TILES = 0.2 / 1.1;
const CONTACT = { along: 0.3, across: 0.26, blur: 1.5 };
const SUPERSAMPLE = 2;
const OUTLINE_POINTS = 48;

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

export function contactShadow(tile: IsoTile): ShadowMask {
  const ellipse = {
    centre: { x: 0, y: 0 },
    axis: { x: Math.SQRT1_2, y: -Math.SQRT1_2 },
    along: CONTACT.along,
    across: CONTACT.across,
  };
  return rasterise(ellipse, CONTACT.blur, tile);
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
  const origin = unproject(tile, { x: x0 + step / 2, y: y0 + step / 2 });
  const right = unproject(tile, { x: step, y: 0 });
  const down = unproject(tile, { x: 0, y: step });
  for (let j = 0; j < height * SUPERSAMPLE; j++) {
    for (let i = 0; i < width * SUPERSAMPLE; i++) {
      const dx = origin.x + i * right.x + j * down.x - centre.x;
      const dy = origin.y + i * right.y + j * down.y - centre.y;
      const u = (dx * axis.x + dy * axis.y) / along;
      const v = (dy * axis.x - dx * axis.y) / across;
      if (u * u + v * v > 1) continue;
      cover[((j / SUPERSAMPLE) | 0) * width + ((i / SUPERSAMPLE) | 0)] += step * step;
    }
  }
  let blurred: Float32Array = cover;
  for (const box of boxesForGaussian(blur)) {
    blurred = boxBlur(blurred, (box - 1) / 2, width, 1, height, width);
    blurred = boxBlur(blurred, (box - 1) / 2, height, width, width, 1);
  }
  const alpha = new Uint8ClampedArray(blurred.length);
  for (let i = 0; i < blurred.length; i++) alpha[i] = blurred[i] * 255;
  return { width, height, origin: { x: -x0, y: -y0 }, alpha };
}

/** Three box blurs come close to a Gaussian, as in PIL's `GaussianBlur`. */
function boxesForGaussian(sigma: number, boxes = 3): number[] {
  const ideal = Math.sqrt((12 * sigma * sigma) / boxes + 1);
  const lower = Math.floor(ideal) % 2 === 0 ? Math.floor(ideal) - 1 : Math.floor(ideal);
  const narrow = Math.round(
    (12 * sigma * sigma - boxes * lower * lower - 4 * boxes * lower - 3 * boxes) / (-4 * lower - 4),
  );
  return Array.from({ length: boxes }, (_, i) => (i < narrow ? lower : lower + 2));
}

/** Each of `lines` runs of `count` values, `stride` apart, starting `gap` apart. */
function boxBlur(
  source: Float32Array,
  radius: number,
  count: number,
  stride: number,
  lines: number,
  gap: number,
): Float32Array {
  const out = new Float32Array(source.length);
  for (let line = 0; line < lines; line++) {
    const start = line * gap;
    let sum = 0;
    for (let k = 0; k <= Math.min(radius, count - 1); k++) sum += source[start + k * stride];
    for (let at = 0; at < count; at++) {
      out[start + at * stride] = sum / (2 * radius + 1);
      if (at + radius + 1 < count) sum += source[start + (at + radius + 1) * stride];
      if (at - radius >= 0) sum -= source[start + (at - radius) * stride];
    }
  }
  return out;
}
