import { describe, expect, it } from 'vitest';
import type { Buyer } from '../net';
import { fits, trades } from './buyers';

const stall: Buyer = { place: 'scrap_stall', name: "The scrap trader's stall", prices: { copper_wire: 6 } };
const clinic: Buyer = { place: 'clinic', name: 'The Clinic', prices: {} };
const cell = { bionic: 'power_cell', name: 'Power cell', price: 100, parts: ['stomach'] } as const;

describe('trades', () => {
  it('is a buyer whose keeper buys a part of the body, fits a bionic or treats', () => {
    expect(trades({ ...clinic, parts: { left_kidney: 100 } })).toBe(true);
    expect(trades({ ...clinic, fittings: [{ ...cell, parts: [...cell.parts] }] })).toBe(true);
    expect(trades({ ...clinic, treatments: [{ effect: null, name: 'Patching you up', price: 20 }] })).toBe(true);
  });

  it('is a buyer with something to sell back', () => {
    const plug = { id: 'usb_c_connector', kind: 'part', name: 'USB-C connector', weight: 0.1, charge: null, on: null } as const;
    const stocked = { ...stall, stock: [{ item: plug, price: 24 }] };
    expect(trades(stocked)).toBe(true);
    expect(fits(stocked)).toBe(false);
  });

  it('is not a buyer of salvage alone, or a clinic with nothing to offer', () => {
    expect(trades(stall)).toBe(false);
    expect(trades({ ...clinic, parts: {}, fittings: [], treatments: [] })).toBe(false);
  });
});
