import { describe, expect, it, vi } from 'vitest';
import type { Item, PlayerStateMessage } from '../net';
import { village } from './content';
import {
  atPlug,
  DARK,
  DIM,
  falloff,
  FADED,
  GLIMMER,
  glowAround,
  hasDark,
  INNER,
  isLit,
  LAMP_RADIUS,
  lampRadius,
  Sight,
} from './darkness';
import { lampOf, LOW, shining, switchLamp } from './lamp';
import { DEPTH } from './depths';
import { pileMarks } from './piles';

vi.mock('phaser', () => ({ default: {} }));

const metro = village.map('metro')!;
const lamp = (charge: number, on: boolean): Item => ({ id: 'lamp', kind: 'lamp', name: 'Lamp', weight: 1, charge, on });
const WIRE: Item = { id: 'copper_wire', kind: 'salvage', name: 'Copper wire', weight: 1.5, charge: null, on: null };
/** Standing in the west tunnel, on the platform's row. */
const TUNNEL = { x: 64, y: 15 };

describe('light on the maps', () => {
  it("reads the metro's dark stretches and leaves the rest lit", () => {
    expect(isLit(metro, 30, 5)).toBe(false);
    expect(isLit(metro, 30, 15)).toBe(true);
    expect(isLit(metro, TUNNEL.x, TUNNEL.y)).toBe(false);
    expect(isLit(metro, 72, 15)).toBe(true);
    expect(isLit(metro, 80, 15)).toBe(false);
    expect(isLit(metro, 95, 15)).toBe(true);
  });

  it('keeps the village lit, and only the metro and the sewers underground', () => {
    for (const map of village.maps.values()) {
      const below = village.map(map.street)!.underground;
      expect(below, map.id).toBe(map.street === 'metro' || map.street === 'sewers');
      if (!below) expect(hasDark(map), map.id).toBe(false);
    }
    expect(hasDark(metro)).toBe(true);
    expect(hasDark(village.map('sewers')!)).toBe(true);
  });
});

describe('Sight', () => {
  it('draws unlit areas dark without the lamp, but for a glimmer around the player', () => {
    const sight = new Sight(metro);
    const glimmer = glowAround(TUNNEL, lamp(1, false));

    expect(glimmer.strength).toBe(GLIMMER.strength);
    expect(sight.darkness(TUNNEL.x + 3, TUNNEL.y, glimmer)).toBe(DARK);
    expect(sight.darkness(TUNNEL.x, TUNNEL.y, glimmer)).toBeGreaterThan(0.5);
    expect(sight.darkness(30, 15, glimmer)).toBe(0);
    expect(sight.see(glimmer)).toBe(false);
  });

  it('lights the dark around the player with the lamp on', () => {
    const sight = new Sight(metro);
    const glow = glowAround(TUNNEL, lamp(1, true));

    expect(glow.radius).toBe(LAMP_RADIUS);
    expect(sight.darkness(TUNNEL.x, TUNNEL.y, glow)).toBe(0);
    expect(sight.darkness(TUNNEL.x + 3, TUNNEL.y, glow)).toBeGreaterThan(0);
    expect(sight.darkness(TUNNEL.x + 3, TUNNEL.y, glow)).toBeLessThan(DARK);
    expect(sight.darkness(TUNNEL.x - 6, TUNNEL.y, glow)).toBe(DARK);
  });

  it('draws what the lamp has lit dimmed once it has moved on, and never hides it again', () => {
    const sight = new Sight(metro);

    expect(sight.see(glowAround(TUNNEL, lamp(1, true)))).toBe(true);
    expect(sight.see(glowAround(TUNNEL, lamp(1, true)))).toBe(false);
    expect(sight.shade(TUNNEL.x, TUNNEL.y)).toBe(DIM);
    expect(sight.shade(TUNNEL.x + 1, TUNNEL.y - 1)).toBe(DIM);
    expect(sight.shade(TUNNEL.x + 6, TUNNEL.y)).toBe(DARK);
    expect(sight.shade(30, 15)).toBe(0);
    expect(sight.darkness(TUNNEL.x, TUNNEL.y, glowAround({ x: 85, y: 15 }, lamp(1, false)))).toBe(DIM);
  });

  it('sees nothing new with a flat lamp, which gives no light', () => {
    const sight = new Sight(metro);
    const flat = lamp(0, true);

    expect(shining(flat)).toBe(false);
    expect(sight.see(glowAround(TUNNEL, flat))).toBe(false);
    expect(sight.darkness(TUNNEL.x + 3, TUNNEL.y, glowAround(TUNNEL, flat))).toBe(DARK);
  });
});

describe('things to pick up in the dark', () => {
  it('glint under the darkness, so it takes the lamp to find them', () => {
    const marks = pileMarks(village, 'metro', [{ at: { map: 'metro', x: 63, y: 15 }, items: [WIRE] }]);

    expect(isLit(metro, 63, 15)).toBe(false);
    expect(marks.map(({ depth }) => depth < DEPTH.dark)).toEqual([true]);
  });
});

describe('the lamp', () => {
  it("is held at chest height over the player's cell", () => {
    expect(glowAround({ x: 10, y: 15 }, lamp(1, true))).toMatchObject({ x: 10.5, y: expect.closeTo(14.9, 5) });
  });

  it('lights fully within its inner share and fades to its edge', () => {
    expect(falloff(0, 4)).toBe(1);
    expect(falloff(INNER * 4, 4)).toBe(1);
    expect(falloff(4 * (1 + INNER) / 2, 4)).toBeCloseTo(0.5);
    expect(falloff(4, 4)).toBe(0);
  });

  it('draws its light in as the battery runs low', () => {
    expect(lampRadius(1)).toBe(LAMP_RADIUS);
    expect(lampRadius(LOW)).toBe(LAMP_RADIUS);
    expect(lampRadius(LOW / 2)).toBeCloseTo(LAMP_RADIUS * (1 + FADED) / 2);
    expect(lampRadius(0)).toBeCloseTo(LAMP_RADIUS * FADED);
  });

  it('switches the other way, but a flat one stays off', () => {
    expect(switchLamp(lamp(0.5, false))).toEqual({ type: 'lamp', on: true });
    expect(switchLamp(lamp(0.5, true))).toEqual({ type: 'lamp', on: false });
    expect(switchLamp(lamp(0, false))).toBeUndefined();
    expect(switchLamp(undefined)).toBeUndefined();
  });

  it('is the lamp the player carries', () => {
    const body = {
      legs: 'present',
      vertebra: 'present',
      left_eye: 'present',
      right_eye: 'present',
      left_kidney: 'present',
      right_kidney: 'present',
    } as const;
    const state = (items: Item[]): PlayerStateMessage => ({
      type: 'player_state',
      player: { money: 0, items, carry_limit: 10, body, hunger: 0 },
    });

    expect(lampOf(state([WIRE, lamp(0.3, true)]))).toEqual(lamp(0.3, true));
    expect(lampOf(state([WIRE]))).toBeUndefined();
    expect(lampOf(undefined)).toBeUndefined();
  });

  it('charges on a plug, as the server reads the tile', () => {
    expect(atPlug({ x: 72, y: 15, map: 'metro' })).toBe(true);
    expect(atPlug({ x: 71.6, y: 15, map: 'metro' })).toBe(true);
    expect(atPlug({ x: 71.4, y: 15, map: 'metro' })).toBe(false);
    expect(atPlug({ x: 13, y: 2, map: 'maker_space_floor_0' })).toBe(true);
    expect(atPlug({ x: 16, y: 2, map: 'coffee_shop_floor_0' })).toBe(true);
    expect(atPlug({ x: 1, y: 2, map: 'noodle_bar_floor_0' })).toBe(true);
    expect(atPlug({ x: 104, y: 15, map: 'metro' })).toBe(false);
    expect(atPlug(undefined)).toBe(false);
  });
});
