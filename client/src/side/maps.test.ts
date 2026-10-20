import { describe, expect, it } from 'vitest';
import { village } from './content';
import { cellOf, climbAt, groundRow, isStanding, isWalkable } from './maps';

const map = (id: string) => village.map(id)!;

describe('the side-view maps', () => {
  it('reads the four streets and every floor', () => {
    expect(village.streets.map(({ id }) => id).sort()).toEqual([
      'banyan_row',
      'high_street',
      'kapok_walk',
      'lychee_lane',
    ]);
    expect(village.floors('coffee_shop').map(({ id }) => id)).toEqual([
      'coffee_shop_floor_0',
      'coffee_shop_floor_1',
      'coffee_shop_floor_2',
    ]);
    expect(village.maps.size).toBe(4 + 31);
  });

  it('puts each floor on its street, four rows above the one below', () => {
    const floors = village.floors('coffee_shop');
    expect(floors.map(({ street, offset }) => [street, offset.x, offset.y])).toEqual([
      ['high_street', 25, 13],
      ['high_street', 25, 9],
      ['high_street', 25, 5],
    ]);
    expect(village.onStreet({ x: 6, y: 2, map: 'coffee_shop_floor_0' })).toEqual({ street: 'high_street', x: 31, y: 15 });
    expect(village.onStreet({ x: 6, y: 15, map: 'high_street' })).toEqual({ street: 'high_street', x: 6, y: 15 });
  });

  it('finds a link by its end tile, and its other end', () => {
    const stairs = village.linkAt('coffee_shop_floor_0', 15, 2)!;
    expect(stairs).toMatchObject({ id: 'coffee_shop_stairs', kind: 'stairs', side: 'outside' });
    expect(village.far(stairs)).toMatchObject({ map: 'coffee_shop_floor_1', x: 11, y: 2, side: 'inside' });
    expect(village.linkAt('high_street', 43, 15)).toMatchObject({ kind: 'door', to: { map: 'coffee_shop_floor_0', x: 18, y: 2 } });
    expect(village.linkAt('high_street', 42, 15)).toBeUndefined();
  });

  it('reads the climbable layer by its marker names', () => {
    expect(climbAt(map('banyan_row'), 54, 16)).toBe('stairs');
    expect(climbAt(map('banyan_row'), 55, 17)).toBe('stairs');
    expect(climbAt(map('lychee_lane'), 45, 13)).toBe('ladder');
    expect(climbAt(map('lychee_lane'), 44, 13)).toBeUndefined();
  });

  it('tells standing cells from open air, walls and climbable cells', () => {
    const street = map('banyan_row');
    expect(isStanding(street, 53, 15)).toBe(true);
    expect(isWalkable(street, 54, 15)).toBe(false);
    expect(isWalkable(street, 54, 16)).toBe(true);
    expect(isStanding(street, 54, 16)).toBe(false);
    expect(isStanding(street, 56, 18)).toBe(true);
    expect(groundRow(street, 53)).toBe(16);
    expect(groundRow(street, 60)).toBe(19);
    const floor = map('house_1_floor_0');
    expect([0, 1, 5, 6].map((x) => isStanding(floor, x, 2))).toEqual([false, true, true, false]);
  });

  it('reads a position as the server does', () => {
    expect(cellOf({ x: 3.49, y: 2 })).toEqual({ x: 3, y: 2 });
    expect(cellOf({ x: 3.5, y: 1.5 })).toEqual({ x: 4, y: 2 });
  });
});
