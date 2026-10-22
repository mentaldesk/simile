import { describe, expect, it } from 'vitest';
import type { Buyer, Item, Pile, Player } from '../net';
import { fitting, listed, pickUpPrompt, sellPrompt } from './salvage';

const salvage = (id: string, name: string, weight: number): Item => ({ id, kind: 'salvage', name, weight, charge: null, on: null });
const LAMP: Item = { id: 'lamp', kind: 'lamp', name: 'Lamp', weight: 1, charge: 1, on: false };
const WIRE = salvage('copper_wire', 'Copper wire', 1.5);
const BOARD = salvage('circuit_board', 'Circuit board', 0.5);
const SERVO = salvage('servo_motor', 'Servo motor', 3);
const RATION: Item = { id: 'ration_pack', kind: 'food', name: 'Ration pack', weight: 0.5, charge: null, on: null };
const body = {
  legs: 'present',
  vertebra: 'present',
  left_eye: 'present',
  right_eye: 'present',
  left_kidney: 'present',
  right_kidney: 'present',
} as const;
const player = (items: Item[], extra: Partial<Player> = {}): Player => ({ money: 12, items, carry_limit: 10, body, hunger: 0, ...extra });
const pile = (items: Item[], money?: number): Pile => ({ at: { map: 'metro', x: 38, y: 12 }, items, ...(money && { money }) });
const TRADER: Buyer = { place: 'scrap_stall', name: "The scrap trader's stall", prices: { copper_wire: 6, circuit_board: 8, servo_motor: 18 } };

describe('listed', () => {
  it('joins with commas and a last and', () => {
    expect(listed([])).toBe('');
    expect(listed(['a'])).toBe('a');
    expect(listed(['a', 'b'])).toBe('a and b');
    expect(listed(['a', 'b', 'c'])).toBe('a, b and c');
  });
});

describe('fitting', () => {
  it('takes each item that still fits, in order, as the server does', () => {
    const full = player([LAMP, SERVO, SERVO, WIRE]);
    expect(fitting(pile([SERVO, BOARD, WIRE]), full)).toEqual({ taken: [BOARD], kept: [SERVO, WIRE] });
  });
});

describe('pickUpPrompt', () => {
  it('says what E picks up of salvage or a secret', () => {
    expect(pickUpPrompt(pile([WIRE]), player([LAMP]))).toBe('Press E to pick up the copper wire.');
    expect(pickUpPrompt(pile([], 25), player([LAMP]))).toBe('Press E to pick up 25 in cash.');
    expect(pickUpPrompt(pile([RATION], 40), player([LAMP]))).toBe('Press E to pick up the ration pack and 40 in cash.');
  });

  it('says what will not fit', () => {
    const laden = player([LAMP, SERVO, SERVO, WIRE]);
    expect(pickUpPrompt(pile([SERVO, BOARD]), laden)).toBe("Press E to pick up the circuit board. The servo motor won't fit.");
    expect(pickUpPrompt(pile([SERVO]), laden)).toBe('The servo motor is too heavy to carry with what you have.');
    expect(pickUpPrompt(pile([SERVO, SERVO]), laden)).toBe('The servo motor and the servo motor are too heavy to carry with what you have.');
    expect(pickUpPrompt(pile([SERVO], 40), laden)).toBe("Press E to pick up 40 in cash. The servo motor won't fit.");
  });

  it('says it is what they left, if it is', () => {
    const left = pile([WIRE, SERVO]);
    expect(pickUpPrompt(left, player([LAMP], { left: [left] }))).toBe('Press E to pick up what you left here.');
    expect(pickUpPrompt(left, player([LAMP, SERVO, SERVO], { left: [left] }))).toBe('Press E to pick up what you can carry of what you left here.');
    expect(pickUpPrompt(left, player([LAMP, SERVO, SERVO, WIRE, WIRE], { left: [left] }))).toBe(
      "You can't carry any more of what you left here.",
    );
  });
});

describe('sellPrompt', () => {
  it('says what E sells, and for how much', () => {
    expect(sellPrompt(TRADER, player([LAMP, WIRE, RATION]))).toBe("Press E to sell your copper wire at the scrap trader's stall for 6.");
    expect(sellPrompt(TRADER, player([WIRE, BOARD]))).toBe("Press E to sell your copper wire and circuit board at the scrap trader's stall for 14.");
    expect(sellPrompt(TRADER, player([WIRE, BOARD, SERVO, WIRE]))).toBe("Press E to sell your salvage at the scrap trader's stall for 38.");
  });

  it('with nothing to sell, says the buyer buys salvage and what they have', () => {
    expect(sellPrompt({ ...TRADER, prices: {} }, player([LAMP, RATION]))).toBe("The scrap trader's stall buys salvage. You have 12.");
  });
});
