import { describe, expect, it } from 'vitest';
import type { Buyer, Corpse, Item, Pile, Player } from '../net';
import { counted, fitting, listed, pickUpPrompt, salvagePrompt, sellPrompt } from './salvage';

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

describe('counted', () => {
  it('says each kind once, with how many', () => {
    expect(counted([WIRE, BOARD, WIRE])).toEqual(['copper wire ×2', 'circuit board']);
    expect(counted([])).toEqual([]);
  });
});

describe('fitting', () => {
  it('takes each item that still fits, in order, as the server does', () => {
    const full = player([LAMP, SERVO, SERVO, WIRE]);
    expect(fitting(pile([SERVO, BOARD, WIRE]), full)).toEqual({ taken: [BOARD], kept: [SERVO, WIRE] });
  });
});

describe('a stack', () => {
  const plastic = (amount: number): Item => ({ id: 'plastic', kind: 'material', name: 'Plastic', weight: 0.5, amount, material: 'plastic', charge: null, on: null });

  it('weighs its whole amount, carried or lying in the pile', () => {
    expect(fitting(pile([plastic(8)]), player([plastic(12)]))).toEqual({ taken: [plastic(8)], kept: [] });
    expect(fitting(pile([plastic(8)]), player([plastic(13)]))).toEqual({ taken: [], kept: [plastic(8)] });
    expect(fitting(pile([plastic(4), plastic(4)]), player([plastic(14)]))).toEqual({ taken: [plastic(4)], kept: [plastic(4)] });
  });

  it('says how much of it there is', () => {
    expect(counted([plastic(8), plastic(0.5)])).toEqual(['plastic ×8.5']);
    expect(counted([plastic(0.5)])).toEqual(['plastic ×0.5']);
    expect(pickUpPrompt(pile([plastic(8)]), player([LAMP]))).toBe('Press E to pick up the plastic ×8.');
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
    expect(pickUpPrompt(pile([SERVO, SERVO]), laden)).toBe('The servo motor ×2 are too heavy to carry with what you have.');
    expect(pickUpPrompt(pile([SERVO], 40), laden)).toBe("Press E to pick up 40 in cash. The servo motor won't fit.");
  });

  it('says only that it is lying here of a pile in left, as that can be a bot\'s haul', () => {
    const left = pile([WIRE, SERVO]);
    expect(pickUpPrompt(left, player([LAMP], { left: [left] }))).toBe("Press E to pick up what's lying here.");
    expect(pickUpPrompt(left, player([LAMP, SERVO, SERVO], { left: [left] }))).toBe("Press E to pick up what you can carry of what's lying here.");
    expect(pickUpPrompt(left, player([LAMP, SERVO, SERVO, WIRE, WIRE], { left: [left] }))).toBe("You can't carry any more of what's lying here.");
  });
});

describe('sellPrompt', () => {
  it('says what the buyer pays for what they carry', () => {
    expect(sellPrompt(TRADER, player([LAMP, WIRE, RATION]))).toBe("Press E to sell at the scrap trader's stall: 6 for your copper wire.");
    expect(sellPrompt(TRADER, player([WIRE, BOARD]))).toBe("Press E to sell at the scrap trader's stall: 14 for your copper wire and circuit board.");
    expect(sellPrompt(TRADER, player([WIRE, BOARD, SERVO, WIRE]))).toBe("Press E to sell at the scrap trader's stall: 38 for your salvage.");
    expect(sellPrompt(TRADER, player([WIRE, BOARD, WIRE]))).toBe(
      "Press E to sell at the scrap trader's stall: 20 for your copper wire ×2 and circuit board.",
    );
    expect(sellPrompt(TRADER, player([WIRE, WIRE]))).toBe("Press E to sell at the scrap trader's stall: 12 for your copper wire ×2.");
  });

  it('with nothing to sell, says the buyer buys salvage and what they have', () => {
    expect(sellPrompt({ ...TRADER, prices: {} }, player([LAMP, RATION]))).toBe("The scrap trader's stall buys salvage. You have 12.");
  });

  it('leaves the lamp out, though the trader buys it', () => {
    const lamp = { ...TRADER, prices: { ...TRADER.prices, lamp: 12 } };
    expect(sellPrompt(lamp, player([LAMP, WIRE]))).toBe("Press E to sell at the scrap trader's stall: 6 for your copper wire.");
    expect(sellPrompt(lamp, player([LAMP]))).toBe("The scrap trader's stall buys salvage. You have 12.");
  });

  it('at the clinic, says E shows what the doctor buys and fits', () => {
    const clinic: Buyer = { place: 'clinic', name: 'The Clinic', prices: { copper_wire: 6 }, parts: { left_kidney: 100 } };
    expect(sellPrompt(clinic, player([WIRE]))).toBe('Press E to see what the Clinic buys and fits.');
  });

  it('with parts to buy back, says E shows what the buyer buys and sells', () => {
    const plug: Item = { id: 'usb_c_connector', kind: 'part', name: 'USB-C connector', weight: 0.1, charge: null, on: null };
    const stall: Buyer = { ...TRADER, stock: [{ item: plug, price: 24 }] };
    expect(sellPrompt(stall, player([WIRE]))).toBe("Press E to see what the scrap trader's stall buys and sells.");
  });
});

describe('salvagePrompt', () => {
  const corpse: Corpse = { id: 'corpse_1', owner: 'player', at: { map: 'metro', x: 38, y: 12 }, money: 5, items: [], bionics: [] };

  it('offers what they can carry', () => {
    expect(salvagePrompt({ corpse, others: 0, takes: true })).toBe('Press E to salvage what you can carry from your body.');
  });

  it('says so when nothing on it can fit', () => {
    expect(salvagePrompt({ corpse, others: 0, takes: false })).toBe("You can't carry any more of what's on your body.");
    expect(salvagePrompt({ corpse, others: 1, takes: false })).toBe("You can't carry any more of what's on the 2 bodies here.");
  });

  it('says which of two on one tile, since they draw as one', () => {
    expect(salvagePrompt({ corpse, others: 1, takes: true })).toBe('Press E to salvage what you can carry from the oldest of the 2 bodies here.');
  });
});
