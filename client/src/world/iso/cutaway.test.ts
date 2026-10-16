import { describe, expect, it } from 'vitest';
import { CUTAWAY_ALPHA, CUTAWAY_SECONDS, fade, hides } from './cutaway';
import { residentDepth } from './depth';
import type { SceneryManifest } from './manifest';
import { feetOf, project } from './projection';
import { FIGURE_HEIGHT } from './tuning';

const manifests = import.meta.glob<SceneryManifest>('../../../../content/art/iso/scenery/*.json', {
  eager: true,
  import: 'default',
});
const afternoon = Object.values(manifests).find(({ set }) => set === 'afternoon')!;
const { tile } = afternoon;
const building = afternoon.objects
  .filter(({ kind }) => kind === 'building')
  .reduce((shortest, next) => (next.height < shortest.height ? next : shortest));
const [x0, y0, x1, y1] = building.footprint;

function figureAt(position: { x: number; y: number }) {
  const feet = feetOf(position);
  const screen = project(tile, feet);
  const depth = residentDepth(feet, tile);
  return { x: screen.x, top: screen.y - FIGURE_HEIGHT, bottom: screen.y, depth };
}

describe('hides', () => {
  it('cuts away a building the player stands behind', () => {
    expect(hides(building, figureAt({ x: x0 + 2, y: y0 - 1 }), tile)).toBe(true);
    expect(hides(building, figureAt({ x: x0 - 1, y: y1 - 2 }), tile)).toBe(true);
  });

  it('leaves it when the player is in front of it', () => {
    expect(hides(building, figureAt({ x: x0 + 2, y: y1 }), tile)).toBe(false);
    expect(hides(building, figureAt({ x: x1, y: y0 + 1 }), tile)).toBe(false);
  });

  it('leaves it when the player is behind it but beside it on screen', () => {
    expect(hides(building, figureAt({ x: x1 + 3, y: y0 - 3 }), tile)).toBe(false);
  });

  it('leaves it when the player is so far behind that they show above its roof', () => {
    expect(hides(building, figureAt({ x: x0 - 12, y: y0 - 12 }), tile)).toBe(false);
  });
});

describe('fade', () => {
  it('fades out and back in over CUTAWAY_SECONDS', () => {
    const half = CUTAWAY_SECONDS / 2;
    expect(fade(1, CUTAWAY_ALPHA, half)).toBeCloseTo((1 + CUTAWAY_ALPHA) / 2);
    expect(fade(CUTAWAY_ALPHA, 1, half)).toBeCloseTo((1 + CUTAWAY_ALPHA) / 2);
  });

  it('stops at the target', () => {
    expect(fade(1, CUTAWAY_ALPHA, 1)).toBe(CUTAWAY_ALPHA);
    expect(fade(CUTAWAY_ALPHA, 1, 1)).toBe(1);
    expect(fade(1, 1, 0.1)).toBe(1);
  });
});
