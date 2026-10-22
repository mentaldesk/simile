// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import type { Item, Meal, PlayerStateMessage } from '../net';
import { COLLAPSED, eatPrompt, feeling, HungerHint, PICK_UP, toEat } from './hunger';

const NOODLES: Meal = { place: 'noodle_bar', name: 'Golden Bowl Noodles', price: 10 };
const HOME: Meal = { place: 'maker_space', name: 'home', price: 0 };
const BUN: Item = { id: 'pork_bun', kind: 'food', name: 'Pork bun', weight: 0.2, charge: null, on: null };
const LAMP: Item = { id: 'lamp', kind: 'lamp', name: 'Lamp', weight: 1, charge: 1, on: false };

function state(hunger: number, { money = 0, items = [LAMP], meal }: { money?: number; items?: Item[]; meal?: Meal } = {}): PlayerStateMessage {
  const body = {
    legs: 'present',
    vertebra: 'present',
    left_eye: 'present',
    right_eye: 'present',
    left_kidney: 'present',
    right_kidney: 'present',
  } as const;
  return { type: 'player_state', player: { money, items, carry_limit: 10, body, hunger }, ...(meal && { meal }) };
}

describe('feeling', () => {
  it('says nothing until they are hungry, then warns them before they collapse', () => {
    expect(feeling(0.49)).toBeUndefined();
    expect(feeling(0.5)).toBe("You're hungry.");
    expect(feeling(0.85)).toBe("You're starving. Eat soon, or you'll collapse.");
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

  it('shows how hungry they are, what to eat and what they left in reach', () => {
    const root = document.createElement('div');
    const hint = new HungerHint(root);

    hint.update(undefined, false);
    expect(shown(root)).toEqual([]);

    hint.update(state(0.2), false);
    expect(shown(root)).toEqual([]);

    hint.update(state(0.75, { meal: HOME }), true);
    expect(shown(root)).toEqual(["You're hungry.", 'Press F to eat at home.', PICK_UP]);
  });

  it('says they collapsed for a few seconds after it', () => {
    const root = document.createElement('div');
    const hint = new HungerHint(root);

    hint.collapsed(1000);
    hint.update(state(0.75), false, 6999);
    expect(shown(root)[0]).toBe(COLLAPSED);
    hint.update(state(0.75), false, 7000);
    expect(shown(root)).not.toContain(COLLAPSED);
  });
});
