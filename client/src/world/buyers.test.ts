import { describe, expect, it } from 'vitest';
import type { Buyer } from '../net';
import { isClinic } from './buyers';

const stall: Buyer = { place: 'scrap_stall', name: "The scrap trader's stall", prices: { copper_wire: 6 } };
const clinic: Buyer = { place: 'clinic', name: 'The Clinic', prices: {} };
const cell = { bionic: 'power_cell', name: 'Power cell', price: 100, parts: ['stomach'] } as const;

describe('isClinic', () => {
  it('is a buyer whose keeper buys a part of the body, fits a bionic or treats', () => {
    expect(isClinic({ ...clinic, parts: { left_kidney: 100 } })).toBe(true);
    expect(isClinic({ ...clinic, fittings: [{ ...cell, parts: [...cell.parts] }] })).toBe(true);
    expect(isClinic({ ...clinic, treatments: [{ effect: null, name: 'Patching you up', price: 20 }] })).toBe(true);
  });

  it('is not a buyer of salvage alone, or a clinic with nothing to offer', () => {
    expect(isClinic(stall)).toBe(false);
    expect(isClinic({ ...clinic, parts: {}, fittings: [], treatments: [] })).toBe(false);
  });
});
