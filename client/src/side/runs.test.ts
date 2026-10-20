import { describe, expect, it } from 'vitest';
import { village } from './content';
import { climbRuns, crossing, distanceTo, pathOf, pointAlong } from './runs';

const map = (id: string) => village.map(id)!;
const cells = (points: readonly { x: number; y: number }[]) => points.map(({ x, y }) => [x, y]);

describe('runs of stairs and ladders within a map', () => {
  it("climbs Banyan Row's stairs from the promenade to the street", () => {
    const [run] = climbRuns(map('banyan_row'));
    expect(run.kind).toBe('stairs');
    expect(cells(run.path.points)).toEqual([
      [56, 18],
      [55, 17],
      [54, 16],
      [53, 15],
    ]);
    expect(run.path.total).toBeCloseTo(3 * Math.SQRT2);
  });

  it('climbs the park ladder from under it and steps off onto the lookout', () => {
    const [run] = climbRuns(map('lychee_lane'));
    expect(run.kind).toBe('ladder');
    expect(cells(run.path.points)).toEqual([
      [45, 15],
      [45, 14],
      [45, 13],
      [45, 12],
      [46, 12],
    ]);
  });

  it('finds none on a street without stairs or a ladder', () => {
    expect(climbRuns(map('high_street'))).toEqual([]);
  });
});

describe('paths', () => {
  const path = pathOf([
    { x: 0, y: 0 },
    { x: 3, y: 4 },
    { x: 3, y: 10 },
  ]);

  it('measures each segment', () => {
    expect(path.lengths).toEqual([5, 6]);
    expect(path.total).toBe(11);
  });

  it('gives the point any distance along, clamped to its ends', () => {
    const out = { x: 0, y: 0 };
    expect(pointAlong(path, 2.5, out)).toEqual({ x: 1.5, y: 2 });
    expect(pointAlong(path, 8, out)).toEqual({ x: 3, y: 7 });
    expect(pointAlong(path, -1, out)).toEqual({ x: 0, y: 0 });
    expect(pointAlong(path, 99, out)).toEqual({ x: 3, y: 10 });
  });

  it('finds how far along a point on it is', () => {
    expect(distanceTo(path, { x: 3, y: 7 })).toBeCloseTo(8);
    expect(distanceTo(path, { x: 1.5, y: 2 })).toBeCloseTo(2.5);
  });
});

describe('crossings between floors', () => {
  it('runs a flight of stairs straight between its ends, in street cells', () => {
    const up = crossing(village, village.linkAt('coffee_shop_floor_0', 15, 2)!)!;
    expect(up.kind).toBe('stairs');
    expect(up.rising).toBe(true);
    expect(cells(up.path.points)).toEqual([
      [40, 15],
      [43, 11],
    ]);
    const down = crossing(village, village.linkAt('coffee_shop_floor_1', 18, 2)!)!;
    expect(down.rising).toBe(false);
    expect(cells(down.path.points)).toEqual([
      [43, 11],
      [40, 15],
    ]);
    expect(down.to).toMatchObject({ map: 'coffee_shop_floor_0', x: 15, y: 2 });
  });

  it('runs a ladder straight up', () => {
    const up = crossing(village, village.linkAt('maker_space_floor_1', 6, 2)!)!;
    expect(up.kind).toBe('ladder');
    expect(cells(up.path.points)).toEqual([
      [8, 11],
      [8, 7],
    ]);
  });

  it('rides a lift in its car: in, up the shaft and out', () => {
    const ride = crossing(village, village.linkAt('gallery_floor_0', 15, 2)!)!;
    expect(ride.kind).toBe('lift');
    expect(ride.to.map).toBe('gallery_floor_2');
    expect(cells(ride.path.points)).toEqual([
      [41, 15],
      [41.5, 15],
      [41.5, 7],
      [42, 7],
    ]);
  });

  it('has no crossing for a door', () => {
    expect(crossing(village, village.linkAt('high_street', 43, 15)!)).toBeUndefined();
  });
});
