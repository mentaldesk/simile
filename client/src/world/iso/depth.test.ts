import { describe, expect, it } from 'vitest';
import { FOOTPRINT } from '../player';
import { GROUND_DEPTH, imageOrigin, residentDepth, sliceAt, sliceDraws } from './depth';
import type { SceneryManifest, SceneryObject } from './manifest';
import { feetOf, project } from './projection';

const manifests = import.meta.glob<SceneryManifest>('../../../../content/art/iso/scenery/*.json', {
  eager: true,
  import: 'default',
});
const afternoon = Object.values(manifests).find(({ set }) => set === 'afternoon')!;
const { tile } = afternoon;
const buildings = afternoon.objects.filter(({ kind }) => kind === 'building');

/** Whether a resident at this position is drawn over the strip of the building they stand in. */
function inFront(building: SceneryObject, position: { x: number; y: number }): boolean | undefined {
  const feet = feetOf(position);
  const slice = sliceAt(building, project(tile, feet).x, tile);
  return slice && residentDepth(feet, tile) > slice.depth;
}

/** The positions a resident can stand at, flush against each wall of a building. */
function against(building: SceneryObject) {
  const [x0, y0, x1, y1] = building.footprint;
  const range = (from: number, to: number) => Array.from({ length: to - from }, (_, i) => from + i);
  return {
    south: range(x0, x1).map((x) => ({ x, y: y1 - FOOTPRINT.top })),
    east: range(y0, y1).map((y) => ({ x: x1 - FOOTPRINT.left, y })),
    north: range(x0, x1).map((x) => ({ x, y: y0 - FOOTPRINT.bottom })),
    west: range(y0, y1).map((y) => ({ x: x0 - FOOTPRINT.right, y })),
  };
}

describe('sliceDraws', () => {
  it('draws each strip of the image as a crop at the image origin', () => {
    for (const object of afternoon.objects) {
      const draws = sliceDraws(object, tile);
      expect(draws.map(({ cropX }) => cropX)).toEqual(object.slices.map(({ x }) => x));
      for (const { x, y } of draws) expect({ x, y }).toEqual(imageOrigin(object, tile));
      const last = object.slices.at(-1)!;
      expect(last.x + last.width).toBe(object.width);
    }
  });

  it('puts an image with its top-left at the projected anchor plus the offset', () => {
    const building = buildings[0];
    const anchor = project(tile, { x: building.anchor[0], y: building.anchor[1] });
    expect(imageOrigin(building, tile)).toEqual({
      x: anchor.x + building.offset[0],
      y: anchor.y + building.offset[1],
    });
  });
});

describe('residentDepth', () => {
  it('sorts a resident in front of every wall that faces the camera', () => {
    for (const building of buildings) {
      const { south, east } = against(building);
      for (const at of [...south, ...east]) {
        expect(inFront(building, at), `${building.id} at ${at.x}, ${at.y}`).toBe(true);
      }
    }
  });

  it('sorts a resident behind every wall that faces away', () => {
    for (const building of buildings) {
      const { north, west } = against(building);
      for (const at of [...north, ...west]) {
        expect(inFront(building, at), `${building.id} at ${at.x}, ${at.y}`).toBe(false);
      }
    }
  });

  it('puts a resident by a south wall in front, though their feet are above the front corner', () => {
    const building = buildings[0];
    const [x0, , x1, y1] = building.footprint;
    const position = { x: Math.floor((x0 + x1) / 2), y: y1 - FOOTPRINT.top };
    const corner = project(tile, { x: x1, y: y1 }).y;
    expect(residentDepth(feetOf(position), tile)).toBeLessThan(corner);
    expect(inFront(building, position)).toBe(true);
  });

  it('draws the resident in front on a tie', () => {
    const feet = { x: 3, y: 4 };
    expect(residentDepth(feet, tile)).toBeGreaterThan(project(tile, feet).y);
  });

  it('keeps the ground under everything', () => {
    for (const { slices } of afternoon.objects) {
      for (const { depth } of slices) expect(depth).toBeGreaterThan(GROUND_DEPTH);
    }
    expect(residentDepth({ x: 0, y: 0 }, tile)).toBeGreaterThan(GROUND_DEPTH);
  });
});

describe('sliceAt', () => {
  it('finds the strip under a screen x, or none off the image', () => {
    const building = buildings[0];
    const left = imageOrigin(building, tile).x;
    expect(sliceAt(building, left, tile)).toBe(building.slices[0]);
    expect(sliceAt(building, left + building.width - 1, tile)).toBe(building.slices.at(-1));
    expect(sliceAt(building, left - 1, tile)).toBeUndefined();
    expect(sliceAt(building, left + building.width, tile)).toBeUndefined();
  });
});
