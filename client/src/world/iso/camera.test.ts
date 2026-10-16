import { describe, expect, it } from 'vitest';
import { isoScroll, TARGET_REACH } from './camera';
import { project, unproject } from './projection';

const TILE = { width: 96, height: 48, px_per_metre_up: 53.443 };
const VIEW = { width: 640, height: 360 };
const MAP = { width: 64, height: 42 };
const REACH = { x: (VIEW.width / 2) * TARGET_REACH + 0.5, y: (VIEW.height / 2) * TARGET_REACH + 0.5 };

const centreOf = (scroll: { x: number; y: number }) => ({
  x: scroll.x + VIEW.width / 2,
  y: scroll.y + VIEW.height / 2,
});

function viewCorners(scroll: { x: number; y: number }) {
  return [
    { x: scroll.x, y: scroll.y },
    { x: scroll.x + VIEW.width, y: scroll.y },
    { x: scroll.x, y: scroll.y + VIEW.height },
    { x: scroll.x + VIEW.width, y: scroll.y + VIEW.height },
  ].map((corner) => unproject(TILE, corner));
}

describe('isoScroll', () => {
  it('centres the view on the target in the middle of the map', () => {
    const target = project(TILE, { x: 31.5, y: 22.5 });
    expect(centreOf(isoScroll(target, VIEW, MAP, TILE, 1))).toEqual(target);
  });

  it('centres on a whole pixel', () => {
    const target = { x: 400.4, y: 1100.6 };
    expect(centreOf(isoScroll(target, VIEW, MAP, TILE, 1))).toEqual({ x: 400, y: 1101 });
  });

  it('keeps the whole view on the diamond as the target nears each edge', () => {
    const nearEdges = [
      { x: 3, y: 21 },
      { x: 61, y: 21 },
      { x: 32, y: 3 },
      { x: 32, y: 39 },
    ];
    for (const point of nearEdges) {
      const target = project(TILE, point);
      const scroll = isoScroll(target, VIEW, MAP, TILE, 1);
      expect(centreOf(scroll)).not.toEqual(target);
      for (const corner of viewCorners(scroll)) {
        expect(corner.x).toBeGreaterThanOrEqual(-0.02);
        expect(corner.y).toBeGreaterThanOrEqual(-0.02);
        expect(corner.x).toBeLessThanOrEqual(MAP.width + 0.02);
        expect(corner.y).toBeLessThanOrEqual(MAP.height + 0.02);
      }
    }
  });

  it('keeps the target in reach everywhere, even in the corners where the view cannot fit', () => {
    for (let x = 0.25; x < MAP.width; x += 0.5) {
      for (let y = 0.25; y < MAP.height; y += 0.5) {
        const target = project(TILE, { x, y });
        const centre = centreOf(isoScroll(target, VIEW, MAP, TILE, 1));
        expect(Math.abs(centre.x - target.x)).toBeLessThanOrEqual(REACH.x);
        expect(Math.abs(centre.y - target.y)).toBeLessThanOrEqual(REACH.y);
      }
    }
  });

  it('sees more of the map when zoomed out, so stops further from the edges', () => {
    const target = project(TILE, { x: 31.5, y: 2 });
    const near = centreOf(isoScroll(target, VIEW, MAP, TILE, 1));
    const far = centreOf(isoScroll(target, VIEW, MAP, TILE, 0.5));
    expect(far.y).toBeGreaterThan(near.y);
  });

  it('centres a map smaller than the view', () => {
    const small = { width: 4, height: 4 };
    const centre = centreOf(isoScroll(project(TILE, { x: 1, y: 3 }), VIEW, small, TILE, 1));
    expect(centre).toEqual(project(TILE, { x: 2, y: 2 }));
  });
});
