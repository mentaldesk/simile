import { describe, expect, it } from 'vitest';
import { CUTAWAY_ALPHA, CUTAWAY_HOLD_SECONDS, CUTAWAY_SECONDS, Cutaway, hides } from './cutaway';
import { imageOrigin, residentDepth } from './depth';
import type { SceneryManifest } from './manifest';
import { feetOf, project } from './projection';
import { FIGURE_HEIGHT } from './tuning';

const manifests = import.meta.glob<SceneryManifest>('../../../../content/art/iso/scenery/*.json', {
  eager: true,
  import: 'default',
});
const afternoon = Object.values(manifests).find(({ set }) => set === 'afternoon')!;
const { tile } = afternoon;
const buildings = afternoon.objects.filter(({ kind }) => kind === 'building');
const building = buildings.reduce((shortest, next) => (next.height < shortest.height ? next : shortest));
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

  it("leaves it when the player is beside its footprint, in its image's margin", () => {
    const corner = buildings.find(({ id }) => id === 'building-1-14')!;
    for (let x = 0.3; x <= 0.5; x += 0.01) {
      expect(hides(corner, figureAt({ x, y: 18.5 }), tile), `x = ${x}`).toBe(false);
    }
    for (const each of buildings) {
      const [fx0, fy0, fx1, fy1] = each.footprint;
      const left = project(tile, { x: fx0, y: fy1 }).x;
      const right = project(tile, { x: fx1, y: fy0 }).x;
      const top = imageOrigin(each, tile).y;
      for (let bottom = top; bottom <= top + each.height + FIGURE_HEIGHT; bottom += 8) {
        for (const x of [left - 1, right + 1]) {
          const figure = { x, top: bottom - FIGURE_HEIGHT, bottom, depth: 0 };
          expect(hides(each, figure, tile), each.id).toBe(false);
        }
      }
    }
  });
});

describe('Cutaway', () => {
  const half = CUTAWAY_SECONDS / 2;

  it('fades out over CUTAWAY_SECONDS while the building hides the player', () => {
    const cutaway = new Cutaway();
    expect(cutaway.update(true, half)).toBeCloseTo((1 + CUTAWAY_ALPHA) / 2);
    expect(cutaway.update(true, half)).toBeCloseTo(CUTAWAY_ALPHA);
    expect(cutaway.update(true, 1)).toBe(CUTAWAY_ALPHA);
  });

  it('holds for CUTAWAY_HOLD_SECONDS after the player comes out, then fades back in', () => {
    const cutaway = new Cutaway();
    cutaway.update(true, 1);
    expect(cutaway.update(false, CUTAWAY_HOLD_SECONDS / 2)).toBe(CUTAWAY_ALPHA);
    expect(cutaway.update(false, CUTAWAY_HOLD_SECONDS / 2)).toBeGreaterThan(CUTAWAY_ALPHA);
    expect(cutaway.update(false, CUTAWAY_SECONDS)).toBe(1);
  });

  it('never brightens while the player keeps grazing the building', () => {
    const cutaway = new Cutaway();
    let alpha = cutaway.alpha;
    for (let frame = 0; frame < 60; frame++) {
      const next = cutaway.update(frame % 3 === 0, 1 / 60);
      expect(next).toBeLessThanOrEqual(alpha);
      alpha = next;
    }
    expect(alpha).toBe(CUTAWAY_ALPHA);
  });
});
