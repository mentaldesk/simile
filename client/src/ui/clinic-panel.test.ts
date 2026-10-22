// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Buyer, ClientMessage, Fitting, Item, Player } from '../net';
import { ClinicPanel, deals, note } from './clinic-panel';

const WIRE: Item = { id: 'copper_wire', kind: 'salvage', name: 'Copper wire', weight: 1.5, charge: null, on: null };
const LEGS: Fitting = { bionic: 'hydraulic_legs', name: 'Hydraulic legs', price: 80, parts: ['legs'] };
const EYE: Fitting = { bionic: 'infrared_eye', name: 'Infrared eye', price: 200, parts: ['left_eye', 'right_eye'] };
const CLINIC: Buyer = {
  place: 'clinic',
  name: 'The Clinic',
  prices: { copper_wire: 6 },
  parts: { left_kidney: 100 },
  fittings: [LEGS, EYE],
};
const body = {
  legs: 'present',
  vertebra: 'present',
  left_eye: 'present',
  right_eye: 'present',
  left_kidney: 'present',
  right_kidney: 'present',
} as const;
const player = (money: number, items: Item[] = []): Player => ({ money, items, carry_limit: 10, body, hunger: 0 });
const DOCTOR = { id: 'annelie', name: 'Annelie Joubert' };

describe('deals', () => {
  it('lists talking, the salvage, the kidney and each fitting in each part it takes', () => {
    expect(deals(CLINIC, player(90, [WIRE, WIRE]), DOCTOR)).toEqual([
      { kind: 'talk', label: 'Talk to Annelie Joubert', npcId: 'annelie' },
      { kind: 'sell', label: 'Sell your copper wire ×2', price: 12 },
      { kind: 'part', label: 'Sell a kidney', price: 100, part: 'left_kidney' },
      { kind: 'fit', label: 'Hydraulic legs, in place of your legs', price: 80, bionic: 'hydraulic_legs', part: 'legs', short: false },
      { kind: 'fit', label: 'Infrared eye, in place of your left eye', price: 200, bionic: 'infrared_eye', part: 'left_eye', short: true },
      { kind: 'fit', label: 'Infrared eye, in place of your right eye', price: 200, bionic: 'infrared_eye', part: 'right_eye', short: true },
    ]);
  });

  it('leaves out what the doctor no longer buys or fits, and talking with nobody to talk to', () => {
    expect(deals({ ...CLINIC, parts: undefined, fittings: [EYE] }, player(0))).toHaveLength(2);
  });
});

describe('note', () => {
  const kidney = deals(CLINIC, player(0))[0]!;
  const eye = deals(CLINIC, player(0))[2]!;

  it('asks once more before anything that cannot be undone', () => {
    expect(note(kidney, false, 0)).toBe('Enter to go ahead.');
    expect(note(kidney, true, 0)).toBe("Enter again to sell a kidney for 100. It can't be undone.");
  });

  it('says what a fitting costs against what they have', () => {
    expect(note(eye, false, 20)).toBe('It costs 200, and you have 20.');
  });
});

describe('ClinicPanel', () => {
  let sent: ClientMessage[];
  let talk: ReturnType<typeof vi.fn<(npcId: string) => void>>;
  let panel: ClinicPanel;

  const section = () => document.querySelector<HTMLElement>('.clinic')!;
  const rows = () => [...document.querySelectorAll('.clinic li')].map((li) => li.textContent);
  const status = () => document.querySelector('.clinic p')!.textContent;
  const press = (key: string) =>
    (document.activeElement ?? section()).dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true }));

  beforeEach(() => {
    sent = [];
    talk = vi.fn<(npcId: string) => void>();
    panel = new ClinicPanel(document.body, (message) => sent.push(message) > 0, talk);
  });

  afterEach(() => document.body.replaceChildren());

  it('opens on what the doctor buys and fits, with what they have', () => {
    panel.open(CLINIC, player(90, [WIRE]), DOCTOR);

    expect(panel.isOpen).toBe(true);
    expect(document.activeElement).toBe(section());
    expect(section().querySelector('b')!.textContent).toBe('The Clinic');
    expect(section().querySelector('small')!.textContent).toBe('You have 90.');
    expect(rows()).toEqual([
      'Talk to Annelie Joubert',
      'Sell your copper wire6',
      'Sell a kidney100',
      'Hydraulic legs, in place of your legs80',
      'Infrared eye, in place of your left eye200',
      'Infrared eye, in place of your right eye200',
    ]);
  });

  it('sells a kidney only on a second Enter', () => {
    panel.open(CLINIC, player(0));
    press('Enter');

    expect(sent).toEqual([]);
    expect(status()).toBe("Enter again to sell a kidney for 100. It can't be undone.");
    expect(section().querySelector('.clinic-armed')!.textContent).toBe('Sell a kidney100');
    press('Enter');
    expect(sent).toEqual([{ type: 'sell_part', part: 'left_kidney' }]);
  });

  it('forgets the first Enter when the choice moves', () => {
    panel.open(CLINIC, player(90));
    press('Enter');
    press('ArrowDown');
    press('ArrowUp');
    press('Enter');

    expect(sent).toEqual([]);
  });

  it('fits the legs, and never what they cannot pay for', () => {
    panel.open(CLINIC, player(90));
    press('ArrowDown');
    press('Enter');
    press('Enter');
    press('ArrowDown');
    press('Enter');
    press('Enter');

    expect(sent).toEqual([{ type: 'fit', bionic: 'hydraulic_legs', part: 'legs' }]);
    expect(status()).toBe('It costs 200, and you have 90.');
  });

  it('sells the salvage at once, and talks to the doctor by closing', () => {
    panel.open(CLINIC, player(0, [WIRE]), DOCTOR);
    press('ArrowDown');
    press('Enter');
    expect(sent).toEqual([{ type: 'sell', item: null }]);

    press('ArrowUp');
    press('Enter');
    expect(talk).toHaveBeenCalledWith('annelie');
    expect(panel.isOpen).toBe(false);
  });

  it('keeps the choice as the offers change, and closes when there is no clinic', () => {
    panel.open(CLINIC, player(100));
    press('ArrowDown');
    panel.update({ ...CLINIC, parts: undefined }, player(100));

    expect(rows()[0]).toBe('Hydraulic legs, in place of your legs80');
    expect(section().querySelector('.clinic-selected')!.textContent).toBe('Hydraulic legs, in place of your legs80');
    panel.update(undefined, player(100));
    expect(panel.isOpen).toBe(false);
  });

  it('chooses the next deal once the chosen one is done, never talking by surprise', () => {
    panel.open(CLINIC, player(0), DOCTOR);
    press('ArrowDown');
    panel.update({ ...CLINIC, parts: undefined }, player(100), DOCTOR);

    expect(section().querySelector('.clinic-selected')!.textContent).toBe('Hydraulic legs, in place of your legs80');
    press('Enter');
    expect(talk).not.toHaveBeenCalled();
  });

  it('closes on Esc or E, and a click chooses and acts', () => {
    panel.open(CLINIC, player(0));
    press('e');
    expect(panel.isOpen).toBe(false);

    panel.open(CLINIC, player(0));
    const kidney = () => document.querySelectorAll<HTMLElement>('.clinic li')[0]!;
    kidney().click();
    kidney().click();
    expect(sent).toEqual([{ type: 'sell_part', part: 'left_kidney' }]);
    press('Escape');
    expect(panel.isOpen).toBe(false);
  });
});
