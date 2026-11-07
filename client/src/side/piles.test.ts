import { describe, expect, it } from 'vitest';
import icons from '../../../content/icons/icons.json';
import type { Corpse, Item, Pile } from '../net';
import { lootIcons, sameCorpses, sameItems } from './piles';

const item = (id: string): Item => ({ id, kind: 'salvage', name: id, weight: 1, charge: null, on: null });
const WIRE = item('copper_wire');
const pile = (map: string, x: number, y: number, money?: number): Pile => ({
  at: { map, x, y },
  items: money ? [] : [WIRE],
  ...(money && { money }),
});

describe('lootIcons', () => {
  it('shows each kind of thing once, a recipe first and cash last, up to three', () => {
    expect(lootIcons({ items: [WIRE] })).toEqual(['copper_wire']);
    expect(lootIcons({ money: 20 })).toEqual(['credits']);
    expect(lootIcons({ items: [WIRE, WIRE, item('lithium_cell')], money: 5 })).toEqual(['copper_wire', 'lithium_cell', 'credits']);
    expect(lootIcons({ items: [item('servo_motor'), WIRE], teaches: 'datajack', money: 5 })).toEqual([
      'schematic',
      'servo_motor',
      'copper_wire',
    ]);
  });

  it('shows a thing without an icon as the unknown item, and nothing for nothing', () => {
    expect(lootIcons({ items: [item('mystery'), WIRE] })).toEqual(['unknown_item', 'copper_wire']);
    expect(lootIcons({ items: [] })).toEqual([]);
  });

  it('has every icon it shows besides the items painted', () => {
    expect(Object.keys(icons.icons)).toEqual(expect.arrayContaining(['schematic', 'credits', 'unknown_item']));
  });
});

describe('sameItems', () => {
  it('has the same piles while a new player_state sends the same ones again', () => {
    const piles = [pile('metro', 30, 15), pile('metro', 40, 15, 20)];
    expect(sameItems(piles, [pile('metro', 30, 15), pile('metro', 40, 15, 20)])).toBe(true);
    expect(sameItems(piles, [pile('metro', 30, 15), pile('metro', 40, 15, 25)])).toBe(false);
    expect(sameItems(piles, [pile('metro', 31, 15), pile('metro', 40, 15, 20)])).toBe(false);
    expect(sameItems(piles, [{ ...pile('metro', 30, 15), items: [] }, pile('metro', 40, 15, 20)])).toBe(false);
    expect(sameItems(piles, piles.slice(1))).toBe(false);
  });
});

const corpse = (more: Partial<Corpse> = {}): Corpse => ({
  id: 'corpse_1',
  owner: 'player',
  at: { map: 'metro', x: 30, y: 15 },
  money: 0,
  items: [],
  bionics: [],
  ...more,
});

describe('sameCorpses', () => {
  it('tells two corpses on one tile apart, and ignores what they hold, which the picture does not show', () => {
    expect(sameCorpses([corpse()], [corpse()])).toBe(true);
    expect(sameCorpses([corpse()], [corpse({ id: 'corpse_2' })])).toBe(false);
    expect(sameCorpses([corpse()], [corpse(), corpse({ id: 'corpse_2' })])).toBe(false);
    expect(sameCorpses([corpse()], [corpse({ at: { map: 'metro', x: 31, y: 15 } })])).toBe(false);
    expect(sameCorpses([corpse({ money: 5, items: [WIRE] })], [corpse()])).toBe(true);
  });
});
