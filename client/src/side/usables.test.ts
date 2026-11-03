import { describe, expect, it, vi } from 'vitest';
import type { Item, Pile } from '../net';
import { clues } from '../world/clues';
import { reachables, type Reachables, type WayPrompt } from '../world/reach';
import { scenery, village } from './content';
import { DEPTH } from './depths';
import { feetOf, furniturePlacement, PPM, xOf } from './layout';
import { Village } from './maps';
import { boxOf, glowing, glowKey, usablesOn, type IconSprite, type Usable, type UsableState } from './usables';

vi.mock('phaser', () => ({ default: {} }));

const WIRE: Item = { id: 'copper_wire', kind: 'salvage', name: 'Copper wire', weight: 1.5, charge: null, on: null };
const ODD: Item = { id: 'mystery', kind: 'salvage', name: 'Mystery', weight: 1, charge: null, on: null };
const state = (more: Partial<UsableState> = {}): UsableState => ({ searched: [], piles: [], clues, ...more });
const on = (street: string, more: Partial<UsableState> = {}, from: Village = village) =>
  usablesOn(from, scenery, from.map(street)!, state(more));
const byId = (usables: Usable[], id: string) => usables.find((usable) => usable.id === id)!;
const furniture = (map: string, name: string) => village.map(map)!.furniture.find((piece) => piece.name === name)!;
const MAKER = village.map('maker_space_floor_0')!;

describe('usablesOn', () => {
  const street = on('high_street', {});

  it("pins Aris's notes over her workbench, her only clue", () => {
    expect(byId(street, 'clue:aris_notes')).toMatchObject({
      kind: 'clue',
      map: 'maker_space_floor_0',
      building: 'maker_space',
      picture: { icon: 'aris_notes', x: xOf(MAKER.offset.x + 3), y: feetOf(MAKER.offset.y + 2) - 2.2 * PPM, depth: DEPTH.stairs + 0.1 },
    });
    expect(street.filter((usable) => usable.kind === 'clue').map(({ id }) => id)).toEqual(['clue:aris_notes']);
  });

  it("draws the datajack's schematic on Aris's bench until it's searched, then a tick on the bench", () => {
    const bench = byId(street, 'maker_space_floor_0/maker_space_bench');
    expect(bench.picture).toMatchObject({ piece: 'furniture/workbench', stretch: expect.any(Number) });
    expect(bench.loot).toEqual([
      expect.objectContaining({ icon: 'schematic', x: xOf(MAKER.offset.x + 5.5), y: bench.picture.y - 0.66 * PPM }),
    ]);
    expect(bench.searched).toBeUndefined();

    const searched = byId(on('high_street', { searched: ['maker_space_bench'] }), 'maker_space_floor_0/maker_space_bench');
    const box = boxOf(scenery, searched.picture);
    expect(searched.loot).toBeUndefined();
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

  it('draws a pile as its icon on the ground, cash as credits, and anything without one as the unknown item', () => {
    const piles: Pile[] = [
      { at: { map: 'metro', x: 30, y: 15 }, items: [WIRE] },
      { at: { map: 'metro', x: 40, y: 15 }, items: [ODD] },
      { at: { map: 'metro', x: 50, y: 15 }, items: [], money: 20 },
    ];
    const usables = on('metro', { piles }).filter(({ kind }) => kind === 'pile');
    expect(usables.map(({ id, picture, loot }) => [id, picture, loot])).toEqual([
      ['pile:metro:30,15', expect.objectContaining({ icon: 'copper_wire', x: xOf(30), y: feetOf(15), originY: 1 }), undefined],
      ['pile:metro:40,15', expect.objectContaining({ icon: 'unknown_item', x: xOf(40), y: feetOf(15) }), undefined],
      ['pile:metro:50,15', expect.objectContaining({ icon: 'credits', x: xOf(50), y: feetOf(15) }), undefined],
    ]);
    expect(usables[0].picture).toMatchObject({ height: expect.closeTo(0.45 * PPM), depth: DEPTH.streetFurniture + 0.1 });
  });

  it('heaps up to three of what a pile holds round its middle, the first in front', () => {
    const LITHIUM: Item = { ...WIRE, id: 'lithium_cell', name: 'Lithium cell' };
    const SERVO: Item = { ...WIRE, id: 'servo_motor', name: 'Servo motor' };
    const pile: Pile = { at: { map: 'metro', x: 30, y: 15 }, items: [WIRE, LITHIUM, WIRE, SERVO, ODD], money: 4 };
    const heap = byId(on('metro', { piles: [pile] }), 'pile:metro:30,15');
    const sprites = [heap.picture, ...heap.loot!] as IconSprite[];

    expect(sprites.map(({ icon }) => icon)).toEqual(['credits', 'copper_wire', 'lithium_cell']);
    expect(sprites.reduce((sum, { x }) => sum + x, 0) / 3).toBeCloseTo(xOf(30));
    expect(sprites[1].x).toBeLessThan(sprites[0].x);
    expect(sprites[2].x).toBeGreaterThan(sprites[0].x);
    expect(sprites.slice(1).every(({ depth, height }) => depth < sprites[0].depth && height < sprites[0].height)).toBe(true);
  });

  it('lays what a searchable holds on it until it is searched', () => {
    const fridge = byId(on('metro'), 'metro/metro_fridge');
    expect(fridge.loot?.map(({ icon }) => icon)).toEqual(['copper_wire', 'lithium_cell']);
    expect(fridge.loot!.every(({ y, depth }) => y < fridge.picture.y && depth > fridge.picture.depth)).toBe(true);
    expect(byId(on('metro', { searched: ['metro_fridge'] }), 'metro/metro_fridge').loot).toBeUndefined();
    expect(byId(on('lychee_lane'), 'house_2_floor_1/house_2_bed').loot?.map(({ icon }) => icon)).toEqual(['credits']);
  });

  it('lays what a jack holds on it only once the datajack can search it', () => {
    expect(byId(on('metro'), 'metro/metro_signal_desk').loot).toBeUndefined();
    expect(byId(on('metro', { jacked: true }), 'metro/metro_signal_desk').loot?.map(({ icon }) => icon)).toEqual(['circuit_board']);
    expect(byId(on('metro', { jacked: true }), 'metro/metro_lift').loot).toBeUndefined();
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

  it("keys a pile's glow by its picture, so taking its first item glows round the next", () => {
    const LAMP: Item = { id: 'lamp', kind: 'lamp', name: 'Lamp', weight: 1, charge: 0.5, on: false };
    const at = { map: 'metro', x: 30, y: 15 };
    const before = byId(on('metro', { piles: [{ at, items: [WIRE, LAMP] }] }), 'pile:metro:30,15');
    const after = byId(on('metro', { piles: [{ at, items: [LAMP] }] }), 'pile:metro:30,15');
    expect(after.picture).toMatchObject({ icon: 'lamp' });
    expect(glowKey(after)).not.toBe(glowKey(before));
    expect(glowKey(byId(on('metro'), 'metro/metro_fridge'))).toBe(glowKey(byId(on('metro', { piles: [] }), 'metro/metro_fridge')));
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
