// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { server } from '../net';
import type { Buyer, Effect, Item, Meal, Pile, Player, PlayerStateMessage, Shut } from '../net';
import { COLLAPSED, eatPrompt, feeling, healthFeeling, HungerHint, onCell, powerFeeling, toEat, when } from './hunger';

const NOODLES: Meal = { place: 'noodle_bar', name: 'Golden Bowl Noodles', price: 10 };
const HOME: Meal = { place: 'maker_space', name: 'home', price: 0 };
const BUN: Item = { id: 'pork_bun', kind: 'food', name: 'Pork bun', weight: 0.2, charge: null, on: null };
const LAMP: Item = { id: 'lamp', kind: 'lamp', name: 'Lamp', weight: 1, charge: 1, on: false };
const WIRE: Item = { id: 'copper_wire', kind: 'salvage', name: 'Copper wire', weight: 1.5, charge: null, on: null };
const TRADER: Buyer = { place: 'scrap_stall', name: "The scrap trader's stall", prices: { copper_wire: 6 } };

type Options = { money?: number; items?: Item[]; meal?: Meal; shut?: Shut; left?: Pile[]; buyer?: Buyer; power?: number };

function state(hunger: number, { money = 0, items = [LAMP], meal, shut, left, buyer, power }: Options = {}): PlayerStateMessage {
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
  return { type: 'player_state', player, ...(meal && { meal }), ...(shut && { shut }), ...(buyer && { buyer }) };
}

describe('feeling', () => {
  it('says nothing until they are hungry, then warns them before they collapse', () => {
    expect(feeling(0.49)).toBeUndefined();
    expect(feeling(0.5)).toBe("You're hungry.");
    expect(feeling(0.85)).toBe("You're starving. Eat soon, or you'll collapse.");
  });
});

describe('healthFeeling', () => {
  const BITE: Effect = { kind: 'rat_bite', strength: 0.2, fades: 0.25, since: '2026-01-01T12:00:00Z' };
  const INFECTION: Effect = { kind: 'infection', strength: 0.4, fades: null, since: '2026-01-01T12:00:00Z' };
  const hurt = (health: number, effects?: Effect[]): Player => ({ ...state(0).player, health, ...(effects && { effects }) });

  it('says nothing while they are well, then that they are hurt, then warns them before they collapse', () => {
    expect(healthFeeling(state(0).player)).toBeUndefined();
    expect(healthFeeling(hurt(0.61))).toBeUndefined();
    expect(healthFeeling(hurt(0.6))).toBe("You're hurt. Rest at home to heal faster.");
    expect(healthFeeling(hurt(0.25))).toBe("You're badly hurt. Rest at home or get patched up at the clinic, or you'll collapse.");
  });

  it('warns of a bite before it turns, and of an infection above all', () => {
    expect(healthFeeling(hurt(0.9, [BITE]))).toBe('A rat bit you. Have the clinic clean it before it turns.');
    expect(healthFeeling(hurt(0.1, [INFECTION]))).toBe("Your bite is infected. It won't heal until the clinic treats it.");
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

// Monday 26 October 2026, 19:52, when the playtest found the noodle bar shut.
const MONDAY_EVENING = '2026-10-26T19:52:00Z';
const SHUT: Shut = { place: 'noodle_bar', name: 'Golden Bowl Noodles', reason: 'closed', opens: '2026-10-27T11:00:00Z' };
const SOLD_OUT: Shut = { ...SHUT, reason: 'sold_out', opens: '2026-10-26T17:00:00Z' };

describe('when', () => {
  it('says today, tomorrow, or the day of the week, at the hour', () => {
    expect(when('2026-10-26T21:30:00Z', MONDAY_EVENING)).toBe('today at 21:30');
    expect(when('2026-10-27T07:00:00Z', MONDAY_EVENING)).toBe('tomorrow at 7:00');
    expect(when('2026-10-28T11:00:00Z', MONDAY_EVENING)).toBe('Wednesday at 11:00');
    expect(when('2026-11-02T09:05:00Z', MONDAY_EVENING)).toBe('next Monday at 9:05');
  });

  it('counts days across midnight by the date, not 24 hours', () => {
    expect(when('2026-10-27T00:30:00Z', '2026-10-26T23:50:00Z')).toBe('tomorrow at 0:30');
    expect(when('2026-10-28T07:00:00Z', '2026-10-27T00:10:00Z')).toBe('tomorrow at 7:00');
  });

  it('names the day before the sim clock is known', () => {
    expect(when('2026-10-27T11:00:00Z', undefined)).toBe('Tuesday at 11:00');
  });
});

describe('shut shops', () => {
  it('says a shop is shut and when it opens, hungry or not', () => {
    expect(eatPrompt(state(0.6, { shut: SHUT }), MONDAY_EVENING)).toBe('Golden Bowl Noodles is shut. Opens tomorrow at 11:00.');
    expect(eatPrompt(state(0, { shut: SHUT }), '2026-10-25T22:00:00Z')).toBe('Golden Bowl Noodles is shut. Opens Tuesday at 11:00.');
    expect(eatPrompt(state(0.6, { shut: { ...SHUT, opens: null } }), MONDAY_EVENING)).toBe('Golden Bowl Noodles is shut.');
  });

  it('says it has sold out for this shift, and when the next starts', () => {
    expect(eatPrompt(state(0.6, { shut: SOLD_OUT }), '2026-10-26T13:00:00Z')).toBe(
      'Golden Bowl Noodles has sold out for this shift. Opens again today at 17:00.',
    );
  });

  it('still offers what they carry first', () => {
    expect(eatPrompt(state(0.6, { shut: SHUT, items: [BUN] }), MONDAY_EVENING)).toBe('Press F to eat your pork bun.');
  });

  it('says nothing of it on a power cell', () => {
    expect(eatPrompt(state(0, { shut: SHUT, power: 0.8 }), MONDAY_EVENING)).toBeUndefined();
  });

  it('reads the day from the sim clock', () => {
    server.dispatch(JSON.stringify({ type: 'clock', time: MONDAY_EVENING, speed: 60 }));
    expect(eatPrompt(state(0.6, { shut: SHUT }))).toBe('Golden Bowl Noodles is shut. Opens tomorrow at 11:00.');
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
