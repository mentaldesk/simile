import { describe, expect, it, vi } from 'vitest';
import type { Item, Pile } from '../net';
import { clues } from '../world/clues';
import { reachables, type Reachables, type WayPrompt } from '../world/reach';
import { scenery, village } from './content';
import { DEPTH } from './depths';
import { feetOf, furniturePlacement, PPM, xOf } from './layout';
import { Village } from './maps';
import { boxOf, glowing, usablesOn, type Usable, type UsableState } from './usables';

vi.mock('phaser', () => ({ default: {} }));

const WIRE: Item = { id: 'copper_wire', kind: 'salvage', name: 'Copper wire', weight: 1.5, charge: null, on: null };
const ODD: Item = { id: 'mystery', kind: 'salvage', name: 'Mystery', weight: 1, charge: null, on: null };
const state = (more: Partial<UsableState> = {}): UsableState => ({ searched: [], piles: [], clues, ...more });
const on = (street: string, more: Partial<UsableState> = {}, from: Village = village) =>
  usablesOn(from, scenery, from.map(street)!, state(more));
const byId = (usables: Usable[], id: string) => usables.find((usable) => usable.id === id)!;
const furniture = (map: string, name: string) => village.map(map)!.furniture.find((piece) => piece.name === name)!;
const MAKER = village.map('maker_space_floor_0')!;
const DOOR = scenery.pieces[scenery.platforms.door];

describe('usablesOn', () => {
  const street = on('high_street', {});

  it("pins Aris's notes over her workbench, and draws the splintered door frame on the maker space's door", () => {
    expect(byId(street, 'clue:aris_notes')).toMatchObject({
      kind: 'clue',
      map: 'maker_space_floor_0',
      building: 'maker_space',
      picture: { icon: 'aris_notes', x: xOf(MAKER.offset.x + 3), y: feetOf(MAKER.offset.y + 2) - 2.2 * PPM, depth: DEPTH.stairs + 0.1 },
    });
    expect(byId(street, 'clue:door_frame').picture).toEqual({
      icon: 'door_frame',
      height: 2.1 * PPM,
      x: xOf(MAKER.offset.x + 14) - DOOR.size[0] / 2,
      y: feetOf(MAKER.offset.y + 2),
      originX: 0,
      originY: 1,
      depth: DEPTH.frame + 0.1,
    });
  });

  it("draws the datajack's schematic on Aris's bench until it's searched, then a tick on the bench", () => {
    const bench = byId(street, 'maker_space_floor_0/maker_space_bench');
    expect(bench.picture).toMatchObject({ piece: 'furniture/workbench', stretch: expect.any(Number) });
    expect(bench.recipe).toMatchObject({ icon: 'schematic', x: xOf(MAKER.offset.x + 5.5), y: bench.picture.y - 0.66 * PPM });
    expect(bench.searched).toBeUndefined();

    const searched = byId(on('high_street', { searched: ['maker_space_bench'] }), 'maker_space_floor_0/maker_space_bench');
    const box = boxOf(scenery, searched.picture);
    expect(searched.recipe).toBeUndefined();
    expect(searched.searched).toMatchObject({ x: box.left + box.width / 2, depth: DEPTH.furniture + 0.1 });
    expect(searched.searched!.y).toBeGreaterThan(box.top);
    expect(searched.searched!.y).toBeLessThan(box.top + box.height);
  });

  it('marks the loft shelf searched, and nothing else', () => {
    const searched = on('high_street', { searched: ['maker_space_shelf'] }).filter((usable) => usable.searched);
    expect(searched.map(({ id }) => id)).toEqual(['maker_space_floor_2/maker_space_shelf']);
  });

  it("finds the metro's appliances and jacks in the furniture that draws them, where the map puts it", () => {
    const metro = village.map('metro')!;
    const usables = on('metro', {});
    const at = (name: string) => ({ piece: expect.stringContaining(name), ...furniturePlacement(furniture('metro', name), metro) });
    expect(byId(usables, 'metro/metro_fridge')).toMatchObject({ kind: 'searchable', picture: at('fridge') });
    expect(byId(usables, 'metro/metro_ticket_machine')).toMatchObject({ kind: 'searchable', picture: at('ticket_machine') });
    expect(byId(usables, 'metro/metro_terminal')).toMatchObject({ kind: 'jack', picture: at('dead_terminal') });
    expect(byId(usables, 'metro/metro_lift')).toMatchObject({ kind: 'jack', picture: at('freight_lift') });
    expect(byId(usables, 'metro/metro_fridge').building).toBeUndefined();
  });

  it("finds the news terminal in the street's furniture", () => {
    expect(byId(street, 'high_street/terminal_1')).toMatchObject({
      kind: 'terminal',
      picture: { piece: expect.stringContaining('news_terminal'), depth: DEPTH.streetFurniture },
    });
  });

  it('draws only things on the street shown and its floors', () => {
    expect(street.some(({ map }) => map === 'metro')).toBe(false);
    expect(new Set(street.map(({ map }) => map))).toEqual(
      new Set(['high_street', 'maker_space_floor_0', 'maker_space_floor_1', 'maker_space_floor_2']),
    );
  });

  it("draws a pile as its first item's icon on the ground, and leaves cash alone to its glint", () => {
    const piles: Pile[] = [
      { at: { map: 'metro', x: 30, y: 15 }, items: [WIRE] },
      { at: { map: 'metro', x: 40, y: 15 }, items: [ODD, WIRE] },
      { at: { map: 'metro', x: 50, y: 15 }, items: [], money: 20 },
    ];
    const usables = on('metro', { piles }).filter(({ kind }) => kind === 'pile');
    expect(usables.map(({ id, picture }) => [id, picture])).toEqual([
      ['pile:metro:30,15', expect.objectContaining({ icon: 'copper_wire', x: xOf(30), y: feetOf(15), originY: 1 })],
      ['pile:metro:40,15', expect.objectContaining({ icon: 'unknown_item', x: xOf(40), y: feetOf(15) })],
    ]);
  });

  it("finds a house's stash in the furniture it's hidden in, and ticks it once searched", () => {
    const house = village.map('house_1_floor_1')!;
    const wardrobe = furniturePlacement(furniture('house_1_floor_1', 'wardrobe'), house);
    const stash = byId(on('lychee_lane'), 'house_1_floor_1/house_1_wardrobe');
    expect(stash).toMatchObject({
      kind: 'searchable',
      building: 'house_1',
      picture: { piece: expect.stringContaining('wardrobe'), x: wardrobe.x, y: wardrobe.y, depth: DEPTH.furniture },
    });
    expect(stash.searched).toBeUndefined();
    expect(byId(on('lychee_lane', { searched: ['house_1_wardrobe'] }), stash.id).searched).toBeDefined();
  });

  it('leaves out a searchable or a jack that no furniture draws', () => {
    const metro = village.map('metro')!;
    const usables = on('metro', {}, new Village([{ ...metro, furniture: [] }]));
    expect(usables.filter(({ kind }) => kind === 'searchable' || kind === 'jack')).toEqual([]);
  });
});

describe('glowing', () => {
  const at = (map: string, x: number, y: number) => ({ map, x, y });
  const from = (more: Partial<Reachables> = {}): Reachables => ({
    ...reachables,
    piles: () => [],
    buyer: () => undefined,
    jacked: () => false,
    searched: () => [],
    ...more,
  });
  const LIFT: WayPrompt = { keys: ['E'], action: 'ride the lift', x: 0, y: 0 };

  it("glows round the clue, searchable, terminal or pile E uses where the player stands", () => {
    const pile: Pile = { at: at('metro', 30, 15), items: [WIRE] };
    expect(glowing(at('maker_space_floor_0', 3, 2), [], from())).toBe('clue:aris_notes');
    expect(glowing(at('maker_space_floor_0', 5, 2), [], from())).toBe('maker_space_floor_0/maker_space_bench');
    expect(glowing(at('metro', 70, 15), [], from())).toBe('metro/metro_fridge');
    expect(glowing(at('high_street', 60, 15), [], from())).toBe('high_street/terminal_1');
    expect(glowing(at('metro', 30, 15), [], from({ piles: () => [pile] }))).toBe('pile:metro:30,15');
  });

  it('glows round nothing out of reach, at a door E takes, or at a searchable already searched', () => {
    expect(glowing(at('maker_space_floor_0', 8, 2), [], from())).toBeUndefined();
    expect(glowing(at('maker_space_floor_0', 3, 2), [LIFT], from())).toBeUndefined();
    expect(glowing(at('maker_space_floor_0', 5, 2), [], from({ searched: () => ['maker_space_bench'] }))).toBeUndefined();
    expect(glowing(undefined, [], from())).toBeUndefined();
  });

  it('glows round a jack only with the datajack, and round the lift E rides with it', () => {
    expect(glowing(at('metro', 104, 15), [], from())).toBeUndefined();
    expect(glowing(at('metro', 100, 15), [], from())).toBeUndefined();
    expect(glowing(at('metro', 104, 15), [], from({ jacked: () => true }))).toBe('metro/metro_terminal');
    expect(glowing(at('metro', 100, 15), [LIFT], from({ jacked: () => true }))).toBe('metro/metro_lift');
  });
});
