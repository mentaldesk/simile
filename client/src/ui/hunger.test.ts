// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import type { Buyer, Item, Meal, Pile, PlayerStateMessage } from '../net';
import { COLLAPSED, eatPrompt, feeling, HungerHint, onCell, powerFeeling, toEat } from './hunger';

const NOODLES: Meal = { place: 'noodle_bar', name: 'Golden Bowl Noodles', price: 10 };
const HOME: Meal = { place: 'maker_space', name: 'home', price: 0 };
const BUN: Item = { id: 'pork_bun', kind: 'food', name: 'Pork bun', weight: 0.2, charge: null, on: null };
const LAMP: Item = { id: 'lamp', kind: 'lamp', name: 'Lamp', weight: 1, charge: 1, on: false };
const WIRE: Item = { id: 'copper_wire', kind: 'salvage', name: 'Copper wire', weight: 1.5, charge: null, on: null };
const TRADER: Buyer = { place: 'scrap_stall', name: "The scrap trader's stall", prices: { copper_wire: 6 } };

type Options = { money?: number; items?: Item[]; meal?: Meal; left?: Pile[]; buyer?: Buyer; power?: number };

function state(hunger: number, { money = 0, items = [LAMP], meal, left, buyer, power }: Options = {}): PlayerStateMessage {
  const body = {
    legs: 'present',
    vertebra: 'present',
    left_eye: 'present',
    right_eye: 'present',
    left_kidney: 'present',
    right_kidney: 'present',
    ...(power !== undefined && { stomach: 'power_cell' as const }),
  } as const;
  const player = { money, items, carry_limit: 10, body, hunger, ...(left && { left }), ...(power !== undefined && power < 1 && { power }) };
  return { type: 'player_state', player, ...(meal && { meal }), ...(buyer && { buyer }) };
}

describe('feeling', () => {
  it('says nothing until they are hungry, then warns them before they collapse', () => {
    expect(feeling(0.49)).toBeUndefined();
    expect(feeling(0.5)).toBe("You're hungry.");
    expect(feeling(0.85)).toBe("You're starving. Eat soon, or you'll collapse.");
  });
});

describe('on a power cell', () => {
  it('knows a cell from a stomach', () => {
    expect(onCell(state(0, { power: 1 }).player)).toBe(true);
    expect(onCell(state(0).player)).toBe(false);
  });

  it('warns as power runs low, and before they collapse', () => {
    expect(powerFeeling(0.31)).toBeUndefined();
    expect(powerFeeling(0.3)).toBe('Your power is low. Charge it at a plug.');
    expect(powerFeeling(0.1)).toBe("Your power cell is nearly flat. Charge it at a plug, or you'll collapse.");
  });

  it('never eats or offers a meal', () => {
    const fed = state(0.9, { meal: HOME, items: [BUN], power: 0.5 });
    expect(toEat(fed)).toBeUndefined();
    expect(eatPrompt(fed)).toBeUndefined();
  });
});

describe('toEat', () => {
  it('has the meal on offer when they can pay, before what they carry', () => {
    expect(toEat(state(0.6, { meal: HOME, items: [BUN] }))).toEqual({ kind: 'meal', meal: HOME });
    expect(toEat(state(0.6, { meal: NOODLES, money: 10, items: [BUN] }))).toEqual({ kind: 'meal', meal: NOODLES });
  });

  it('eats the first food they carry when there is no meal they can pay for', () => {
    expect(toEat(state(0.6, { meal: NOODLES, money: 9.5, items: [LAMP, BUN] }))).toEqual({ kind: 'item', item: BUN });
    expect(toEat(state(0.6, { items: [BUN] }))).toEqual({ kind: 'item', item: BUN });
  });

  it('eats nothing with nothing to eat, or before they are peckish', () => {
    expect(toEat(state(0.9, { meal: NOODLES, money: 3 }))).toBeUndefined();
    expect(toEat(state(0.29, { meal: HOME, items: [BUN] }))).toBeUndefined();
    expect(toEat(undefined)).toBeUndefined();
  });
});

describe('eatPrompt', () => {
  it('says what F eats', () => {
    expect(eatPrompt(state(0.3, { meal: HOME }))).toBe('Press F to eat at home.');
    expect(eatPrompt(state(0.3, { meal: NOODLES, money: 12.5 }))).toBe('Press F to eat at Golden Bowl Noodles for 10.');
    expect(eatPrompt(state(0.3, { items: [BUN] }))).toBe('Press F to eat your pork bun.');
  });

  it('once they are hungry with nothing F can eat, says where they could', () => {
    expect(eatPrompt(state(0.49))).toBeUndefined();
    expect(eatPrompt(state(0.5))).toBe('Eat at home, or at the café or the noodle bar.');
    expect(eatPrompt(state(0.5, { meal: NOODLES, money: 4.25 }))).toBe(
      'A meal at Golden Bowl Noodles is 10, and you have 4.25.',
    );
  });
});

describe('HungerHint', () => {
  const shown = (root: HTMLElement) =>
    [...root.querySelectorAll<HTMLElement>('.hunger-hint div')].filter((line) => !line.hidden).map((line) => line.textContent);

  it('shows how hungry they are, what to eat, what they left in reach and what they can sell', () => {
    const root = document.createElement('div');
    const hint = new HungerHint(root);
    const left: Pile = { at: { map: 'kapok_walk', x: 12, y: 15 }, items: [BUN] };

    hint.update(undefined, undefined);
    expect(shown(root)).toEqual([]);

    hint.update(state(0.2), undefined);
    expect(shown(root)).toEqual([]);

    hint.update(state(0.75, { meal: HOME, left: [left] }), left);
    expect(shown(root)).toEqual(["You're hungry.", 'Press F to eat at home.', 'Press E to pick up what you left here.']);

    hint.update(state(0.2, { items: [LAMP, WIRE], buyer: TRADER }), undefined);
    expect(shown(root)).toEqual(["Press E to sell your copper wire at the scrap trader's stall for 6."]);
  });

  it('shows their power in place of hunger once a cell is in', () => {
    const root = document.createElement('div');
    const hint = new HungerHint(root);

    hint.update(state(0.9, { meal: HOME, power: 1 }), undefined);
    expect(shown(root)).toEqual([]);

    hint.update(state(0.9, { meal: HOME, power: 0.2 }), undefined);
    expect(shown(root)).toEqual(['Your power is low. Charge it at a plug.']);
  });

  it('says they collapsed for a few seconds after it', () => {
    const root = document.createElement('div');
    const hint = new HungerHint(root);

    hint.collapsed('hunger', 1000);
    hint.update(state(0.75), undefined, 6999);
    expect(shown(root)[0]).toBe(COLLAPSED.hunger);
    hint.update(state(0.75), undefined, 7000);
    expect(shown(root)).not.toContain(COLLAPSED.hunger);
  });

  it('says why they collapsed', () => {
    const root = document.createElement('div');
    const hint = new HungerHint(root);

    hint.collapsed('power', 1000);
    hint.update(state(0, { power: 0.25 }), undefined, 2000);
    expect(shown(root)[0]).toBe('Your power cell ran flat. You collapsed and woke at home.');
  });
});
