import { describe, expect, it, vi } from 'vitest';
import type { Item, Pile } from '../net';
import { village } from './content';
import { DEPTH } from './depths';
import { feetOf, PPM, xOf } from './layout';
import { pileMarks, sameItems } from './piles';

vi.mock('phaser', () => ({ default: {} }));

const WIRE: Item = { id: 'copper_wire', kind: 'salvage', name: 'Copper wire', weight: 1.5, charge: null, on: null };
const pile = (map: string, x: number, y: number, money?: number): Pile => ({
  at: { map, x, y },
  items: money ? [] : [WIRE],
  ...(money && { money }),
});

describe('pileMarks', () => {
  it('glints over each pile on the street shown and its floors, cash apart', () => {
    const piles = [pile('high_street', 20, 15), pile('maker_space_floor_0', 5, 2, 25), pile('kapok_walk', 12, 15)];

    const marks = pileMarks(village, 'high_street', piles);

    expect(marks).toEqual([
      { x: xOf(20), y: expect.closeTo(feetOf(15) - 0.3 * PPM), depth: DEPTH.streetFurniture + 0.5, cash: false },
      { x: xOf(2 + 5), y: expect.closeTo(feetOf(13 + 2) - 0.3 * PPM), depth: DEPTH.furniture + 0.25, cash: true },
    ]);
  });

  it('has the same piles while a new player_state sends the same ones again', () => {
    const piles = [pile('metro', 30, 15), pile('metro', 40, 15, 20)];
    expect(sameItems(piles, [pile('metro', 30, 15), pile('metro', 40, 15, 20)])).toBe(true);
    expect(sameItems(piles, [pile('metro', 30, 15), pile('metro', 40, 15, 25)])).toBe(false);
    expect(sameItems(piles, [pile('metro', 31, 15), pile('metro', 40, 15, 20)])).toBe(false);
    expect(sameItems(piles, [{ ...pile('metro', 30, 15), items: [] }, pile('metro', 40, 15, 20)])).toBe(false);
    expect(sameItems(piles, piles.slice(1))).toBe(false);
  });

  it('has none for maps it does not know', () => {
    expect(pileMarks(village, 'high_street', [pile('sewers', 1, 1)])).toEqual([]);
  });
});
