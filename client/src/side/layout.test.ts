import { describe, expect, it } from 'vitest';
import { scenery, village } from './content';
import {
  coverCrop,
  dollhouse,
  feetOf,
  frontPlacement,
  furniturePlacement,
  groundRuns,
  ledges,
  muralRect,
  PPM,
  roofHeight,
  stretchParts,
  stretchWidth,
  TILE,
  xOf,
} from './layout';

const map = (id: string) => village.map(id)!;

describe('the street layout', () => {
  it('works at the scenery scale, 120 px a metre and 1.1 m a tile', () => {
    expect(scenery.ppm).toBe(PPM);
    expect(TILE).toBeCloseTo(132);
    expect(xOf(0)).toBeCloseTo(66);
    expect(feetOf(15)).toBeCloseTo(16 * 132);
  });

  it('stands every front on its building, its walls as wide and tall as the map has it', () => {
    for (const street of village.streets) {
      for (const building of street.buildings) {
        const entry = scenery.buildings[building.name];
        expect(entry?.street).toBe(street.id);
        const piece = scenery.pieces[entry.front];
        const placed = frontPlacement(building, piece);
        const walls = piece.width! * PPM;
        expect(placed.x - walls / 2).toBeCloseTo(building.x * TILE, 0);
        expect(placed.x + walls / 2).toBeCloseTo((building.x + building.w) * TILE, 0);
        expect(placed.y).toBeCloseTo(feetOf(15), 5);
        expect(piece.eaves! * PPM).toBeCloseTo(building.h * TILE, 0);
        expect(roofHeight(piece)).toBeCloseTo(piece.size[1] * piece.anchor![1] - piece.eaves! * PPM, 0);
      }
    }
  });

  it('leaves a mural wall blank from its bottom to its top storey, up to the eaves', () => {
    const corner = muralRect({ x: 20, y: 15, width: 4, bottom: 0.7, top: 2.85 }, 12.1);
    expect(corner.x).toBeCloseTo(20 * TILE);
    expect(corner.width).toBeCloseTo(4 * TILE);
    expect(corner.y + corner.height).toBeCloseTo(feetOf(15) - 0.7 * 4.4 * PPM);
    expect(corner.y).toBeCloseTo(feetOf(15) - 12.1 * PPM);
    const low = muralRect({ x: 19, y: 15, width: 3, bottom: 0.15, top: 1.85 });
    expect(low.height).toBeCloseTo(1.7 * 4.4 * PPM);
  });

  it('crops a mural painted at another aspect to cover its wall, centred, unstretched', () => {
    const wall = { x: 0, y: 0, width: 288, height: 614 };
    const tall = coverCrop(288, 445, wall);
    expect(tall.height).toBeCloseTo(445);
    expect(tall.width).toBeCloseTo((288 * 445) / 614);
    expect(tall.x).toBeCloseTo((288 - tall.width) / 2);
    expect(tall.y).toBe(0);
    expect(tall.width * tall.scale).toBeCloseTo(288);
    expect(tall.height * tall.scale).toBeCloseTo(614);
    const wide = coverCrop(400, 100, { x: 5, y: 5, width: 100, height: 100 });
    expect(wide).toEqual({ x: 150, y: 0, width: 100, height: 100, scale: 1 });
    expect(coverCrop(144, 307, wall)).toEqual({ x: 0, y: 0, width: 144, height: 307, scale: 2 });
  });

  it('stands furniture on its cells, and hangs what is above a room on its wall', () => {
    const cafe = map('coffee_shop_floor_0');
    const counter = cafe.furniture.find(({ name }) => name === 'counter')!;
    const board = cafe.furniture.find(({ name }) => name === 'menu_board')!;
    expect(furniturePlacement(counter, cafe)).toMatchObject({ x: (25 + 3 + 1.5) * TILE, originY: 1 });
    expect(furniturePlacement(counter, cafe).y).toBeGreaterThan(feetOf(15));
    expect(furniturePlacement(board, cafe)).toEqual({ x: (25 + 2 + 1.5) * TILE, y: (13 + 0.5) * TILE, originX: 0.5, originY: 0.5 });
    const bench = map('high_street').furniture.find(({ name }) => name === 'bench')!;
    expect(furniturePlacement(bench, map('high_street')).originY).toBe(1);
  });

  it('stretches a run by repeating its middle and keeping its ends', () => {
    const counter = map('coffee_shop_floor_0').furniture.find(({ name }) => name === 'bar_counter')!;
    const width = stretchWidth(counter);
    expect(width).toBe(Math.round(5 * TILE * 0.96));
    const parts = stretchParts(width, 281);
    expect(parts.end).toBe(42);
    expect(parts.middle * parts.repeats).toBeGreaterThanOrEqual(parts.fill);
    expect(2 * parts.end + parts.fill).toBe(width);
  });

  it('lays the pavement, the square, the park and the promenade below Banyan Row', () => {
    const high = groundRuns(map('high_street'), scenery);
    expect(high.map(({ key, x0, x1 }) => [key, x0, x1])).toEqual([
      ['layers/ground-street', 0, 45],
      ['layers/ground-plaza', 45, 65],
      ['layers/ground-street', 65, 84],
    ]);
    const banyan = groundRuns(map('banyan_row'), scenery);
    expect(banyan.at(-1)).toEqual({ key: 'layers/ground-promenade', x0: 54, x1: 68, row: 19 });
    expect(banyan[0].row).toBe(16);
  });

  it('finds the lookout ledge the park ladder leads to', () => {
    expect(ledges(map('lychee_lane'))).toEqual([{ x0: 46, x1: 49, row: 13 }]);
    expect(ledges(map('high_street'))).toEqual([]);
  });

  it('stacks a dollhouse floor on floor, each floor line four rows above the one below', () => {
    const building = map('high_street').buildings.find(({ name }) => name === 'coffee_shop')!;
    const house = dollhouse(building, village.floors('coffee_shop'));
    expect(house.floors.map(({ floorLine, ceiling }) => [floorLine / TILE, ceiling / TILE])).toEqual([
      [16, 12],
      [12, 8],
      [8, 5],
    ]);
    expect([house.left / TILE, house.right / TILE, house.top / TILE, house.ground / TILE]).toEqual([25, 45, 5, 16]);
  });
});
