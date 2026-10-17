import { describe, expect, it } from 'vitest';
import type { Point } from '../view';
import { GROUND_DEPTH } from './depth';
import type { CharacterLights } from './lighting';
import { project } from './projection';
import { contactShadow, dropShadow, SHADOW_DEPTH, type ShadowMask } from './shadow';

const TILE = { width: 96, height: 48, px_per_metre_up: 53.443 };
const { sets } = Object.values(
  import.meta.glob<CharacterLights>('../../../../content/art/iso/characters/lights.json', {
    eager: true,
    import: 'default',
  }),
)[0];

/** The mask's alpha, 0 to 1, at a point in tiles from the feet. */
function alphaAt(mask: ShadowMask, tiles: Point): number {
  const screen = project(TILE, tiles);
  const [x, y] = [Math.floor(mask.origin.x + screen.x), Math.floor(mask.origin.y + screen.y)];
  if (x < 0 || y < 0 || x >= mask.width || y >= mask.height) return 0;
  return mask.alpha[y * mask.width + x] / 255;
}

describe('dropShadow', () => {
  it.each(Object.entries(sets))('runs from the feet to the tip in the %s', (_, { shadow }) => {
    const mask = dropShadow(shadow, TILE);
    const [dx, dy] = shadow.direction;
    const along = (t: number, across = 0) => ({ x: dx * t - dy * across, y: dy * t + dx * across });

    expect(mask.alpha.length).toBe(mask.width * mask.height);
    expect(alphaAt(mask, along(0))).toBeGreaterThan(0.3);
    expect(alphaAt(mask, along(shadow.length / 2))).toBeGreaterThan(0.8);
    expect(alphaAt(mask, along(shadow.length - 0.05))).toBeGreaterThan(0.3);
    expect(alphaAt(mask, along(-0.6))).toBeLessThan(0.02);
    expect(alphaAt(mask, along(shadow.length + 0.6))).toBeLessThan(0.02);
    expect(alphaAt(mask, along(shadow.length / 2, 0.6))).toBeLessThan(0.02);
  });

  it('ends at the tip in lights.json, in screen px from the feet', () => {
    for (const { shadow } of Object.values(sets)) {
      const [dx, dy] = shadow.direction;
      const tip = project(TILE, { x: dx * shadow.length, y: dy * shadow.length });
      expect(tip.x).toBeCloseTo(shadow.tip[0], 0);
      expect(tip.y).toBeCloseTo(shadow.tip[1], 0);
    }
  });

  it('is longer in the evening than at noon', () => {
    const size = ({ shadow }: { shadow: typeof sets.night.shadow }) => {
      const mask = dropShadow(shadow, TILE);
      return Math.hypot(mask.width, mask.height);
    };
    expect(size(sets.evening)).toBeGreaterThan(3 * size(sets.afternoon));
  });
});

describe('contactShadow', () => {
  const mask = contactShadow(TILE);

  const onScreen = (x: number, y: number) =>
    mask.alpha[Math.floor(mask.origin.y + y) * mask.width + Math.floor(mask.origin.x + x)] / 255;

  it('is dark under the feet and gone half a tile away', () => {
    expect(alphaAt(mask, { x: 0, y: 0 })).toBeGreaterThan(0.95);
    for (const [x, y] of [[0.5, 0], [0, 0.5], [-0.5, 0], [0, -0.5]]) {
      expect(alphaAt(mask, { x, y })).toBeLessThan(0.05);
    }
  });

  it('is wider across the screen than up it, and centred on the feet', () => {
    for (const x of [-15, 15]) expect(onScreen(x, 0)).toBeGreaterThan(0.5);
    for (const y of [-14, 14]) expect(onScreen(0, y)).toBeLessThan(0.05);
    expect(mask.origin.x * 2).toBeCloseTo(mask.width, -1);
    expect(mask.origin.y * 2).toBeCloseTo(mask.height, -1);
  });
});

it('draws shadows on the ground, under everything else', () => {
  expect(SHADOW_DEPTH).toBeGreaterThan(GROUND_DEPTH + 1e-3);
  expect(SHADOW_DEPTH).toBeLessThan(-1e5);
});
