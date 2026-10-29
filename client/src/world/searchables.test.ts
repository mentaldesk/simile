import { describe, expect, it } from 'vitest';
import { maps } from './assets';
import { interactablesOf, type Interactable } from './interactables';
import { reachables, usedByE } from './reach';
import { foundIn, listed, searches, toSearch } from './searchables';

const thing = (map: string, id: string): Interactable => interactablesOf(map, maps[map]!).find((each) => each.id === id)!;
const BENCH = thing('maker_space_floor_0', 'maker_space_bench');
const SHELF = thing('maker_space_floor_2', 'maker_space_shelf');
const TERMINAL = thing('metro', 'metro_terminal');
const at = (map: string, x: number, y = 2) => ({ x, y, map });

describe('searchable things', () => {
  it('read what they hold and teach from the maps', () => {
    expect(BENCH).toMatchObject({ kind: 'searchable', label: "Aris's bench", teaches: 'datajack', prompt: "Search Aris's bench" });
    expect(BENCH.items).toBeUndefined();
    expect(SHELF.items?.map(({ id }) => id)).toEqual(['usb_c_connector', 'copper_wire']);
    expect(thing('metro', 'metro_fridge').prompt).toBe('Search the dead fridge');
  });

  it('are searched once, and a jack only while it holds something and the datajack works it', () => {
    expect(searches(BENCH, [], false)).toBe(true);
    expect(searches(BENCH, ['maker_space_bench'], true)).toBe(false);
    expect(searches(TERMINAL, [], true)).toBe(false);
    const holding = { ...TERMINAL, teaches: 'infrared_eye' as const };
    expect(searches(holding, [], false)).toBe(false);
    expect(searches(holding, [], true)).toBe(true);
  });

  it('come first for E until searched, then leave E to what else is there', () => {
    const fresh = { ...reachables, searched: () => [] };
    const done = { ...reachables, searched: () => ['maker_space_bench'] };
    expect(usedByE(at('maker_space_floor_0', 5), fresh)).toMatchObject({ kind: 'searchable', interactable: { id: 'maker_space_bench' } });
    expect(usedByE(at('maker_space_floor_0', 5), done)).toBeUndefined();
  });

  it('say what E finds in them', () => {
    expect(foundIn(BENCH)).toBe('Schematic found: the clinic can fit the datajack.');
    expect(foundIn(SHELF)).toBe('You find a USB-C connector and a copper wire.');
    expect(foundIn({ ...SHELF, items: [], teaches: 'power_cell_2' })).toBe('Schematic found: the clinic can fit the power cell, grade 2.');
    expect(foundIn({ ...SHELF, teaches: 'datajack' })).toBe('You find a USB-C connector and a copper wire. Schematic found: the clinic can fit the datajack.');
    expect(foundIn({ ...SHELF, items: undefined })).toBe("There's nothing in the storage shelf.");
    const battery = { id: 'old_battery', kind: 'salvage', name: 'Old battery', weight: 2, charge: null, on: null } as const;
    const coil = { ...battery, id: 'copper_coil', name: 'Copper coil' };
    expect(listed([battery, battery, coil, battery])).toBe('three old batteries and a copper coil');
  });

  it('read the cash in them from the maps, and say it', () => {
    const mattress = thing('house_2_floor_1', 'house_2_bed');
    const tin = thing('house_2_floor_0', 'house_2_kitchen');
    expect(mattress).toMatchObject({ label: 'Under the mattress', money: 10 });
    expect(SHELF.money).toBeUndefined();
    expect(foundIn(mattress)).toBe('You find 10 credits.');
    expect(foundIn(tin)).toBe('You find 2 credits and a ration bar.');
    expect(foundIn({ ...SHELF, money: 1 })).toBe('You find 1 credit, a USB-C connector and a copper wire.');
    expect(toSearch([], false, ['house_2_floor_1'])).toEqual([{ at: { map: 'house_2_floor_1', x: 3, y: 2 }, items: [], money: 10 }]);
    expect(toSearch(['house_2_bed'], false, ['house_2_floor_1'])).toEqual([]);
  });

  it('glint until searched, each the same pile every time', () => {
    const first = toSearch([], false);
    const bench = first.find(({ at }) => at.map === 'maker_space_floor_0');
    expect(bench).toMatchObject({ at: { map: 'maker_space_floor_0', x: 6, y: 2 }, items: [] });
    expect(toSearch([], false)).toEqual(first);
    expect(toSearch([], false).every((pile, i) => pile === first[i])).toBe(true);
    expect(toSearch(['maker_space_bench'], false)).not.toContain(bench);
    expect(new Set(toSearch([], false, ['metro']).map(({ at }) => at.map))).toEqual(new Set(['metro']));
  });
});
