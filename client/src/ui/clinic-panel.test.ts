// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Buyer, ClientMessage, Fitting, Item, Player, Recipe } from '../net';
import { ClinicPanel, deals, needed, needs, note } from './clinic-panel';

const WIRE: Item = { id: 'copper_wire', kind: 'salvage', name: 'Copper wire', weight: 1.5, charge: null, on: null };
const LEGS: Fitting = { bionic: 'hydraulic_legs', name: 'Hydraulic legs', price: 80, parts: ['legs'] };
const EYE: Fitting = { bionic: 'infrared_eye', name: 'Infrared eye', price: 200, parts: ['left_eye', 'right_eye'] };
const JACK: Fitting = { bionic: 'datajack', name: 'Datajack', price: 100, parts: ['vertebra'] };
const JACK_RECIPE: Recipe = {
  bionic: 'datajack',
  name: 'Datajack',
  parts: { copper_wire: 3, usb_c_connector: 1 },
  credits: 100,
  replaces: ['vertebra'],
  after: ['power_cell'],
};
const CELL_RECIPE: Recipe = {
  bionic: 'power_cell',
  name: 'Power cell',
  parts: { lithium_cell: 3 },
  credits: 100,
  replaces: ['stomach'],
  after: [],
};
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
      { kind: 'fit', label: 'Hydraulic legs, in place of your legs', price: 80, bionic: 'hydraulic_legs', part: 'legs', needs: [], short: false },
      { kind: 'fit', label: 'Infrared eye, in place of your left eye', price: 200, bionic: 'infrared_eye', part: 'left_eye', needs: [], short: true },
      { kind: 'fit', label: 'Infrared eye, in place of your right eye', price: 200, bionic: 'infrared_eye', part: 'right_eye', needs: [], short: true },
    ]);
  });

  it('says what each fitting from a recipe uses up, what they have of it, and the recipes she buys', () => {
    const buyer: Buyer = { ...CLINIC, parts: undefined, fittings: [JACK], recipes: { datajack: 15 } };
    const found = deals(buyer, player(500, [WIRE, WIRE]), undefined, [CELL_RECIPE, JACK_RECIPE]);

    expect(found).toEqual([
      { kind: 'sell', label: 'Sell your copper wire ×2', price: 12 },
      {
        kind: 'fit',
        label: 'Datajack, in place of a vertebra',
        price: 100,
        bionic: 'datajack',
        part: 'vertebra',
        needs: [
          { name: 'copper wire', count: 3, have: 2 },
          { name: 'usb c connector', count: 1, have: 0 },
        ],
        short: true,
      },
      { kind: 'recipe', label: 'Sell your recipe: Datajack', price: 15, bionic: 'datajack' },
    ]);
    expect(needed(needs(JACK_RECIPE, [WIRE]))).toBe('copper wire 1/3 · usb c connector 0/1');
  });

  it('is short of nothing once they have the parts and the credits', () => {
    const connector: Item = { id: 'usb_c_connector', kind: 'part', name: 'USB-C connector', weight: 0.1, charge: null, on: null };
    const [fit] = deals({ ...CLINIC, prices: {}, parts: undefined, fittings: [JACK] }, player(100, [WIRE, WIRE, WIRE, connector]), undefined, [JACK_RECIPE]);

    expect(fit).toMatchObject({ kind: 'fit', short: false, needs: [{ have: 3 }, { name: 'usb-c connector', have: 1 }] });
  });

  it('leaves out what the doctor no longer buys or fits, and talking with nobody to talk to', () => {
    expect(deals({ ...CLINIC, parts: undefined, fittings: [EYE] }, player(0))).toHaveLength(2);
  });
});

const TREATED: Buyer = {
  ...CLINIC,
  treatments: [
    { effect: null, name: 'Patch up', price: 15 },
    { effect: 'infection', name: 'Treat the infection', price: 25 },
  ],
};

describe('treatments', () => {
  it('lists each treatment after talking, and what it costs against what they have', () => {
    const [, patch, infection] = deals(TREATED, player(20), DOCTOR);

    expect(patch).toEqual({ kind: 'treat', label: 'Patch up', price: 15, effect: null, short: false });
    expect(infection).toMatchObject({ kind: 'treat', effect: 'infection', short: true });
    expect(note(patch, false, 20)).toBe('Enter to go ahead.');
    expect(note(infection, false, 20)).toBe('It costs 25, and you have 20.');
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

  it('says which part a fitting is short of first', () => {
    const [jack] = deals({ ...CLINIC, prices: {}, parts: undefined, fittings: [JACK] }, player(500, [WIRE]), undefined, [JACK_RECIPE]);

    expect(note(jack, false, 500)).toBe('It needs 3 copper wire, and you have 1.');
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

  it('treats them on one Enter, and never for what they cannot pay', () => {
    panel.open(TREATED, player(20));
    press('Enter');
    press('ArrowDown');
    press('Enter');

    expect(sent).toEqual([{ type: 'treat', effect: null }]);
    expect(section().querySelector('.clinic-short')!.textContent).toBe('Treat the infection25');
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

  it('shows what a fitting needs under it, and sells a recipe on one Enter', () => {
    const buyer: Buyer = { ...CLINIC, prices: {}, parts: undefined, fittings: [JACK], recipes: { datajack: 15 } };
    panel.open(buyer, player(500, [WIRE]), undefined, [JACK_RECIPE]);

    expect(rows()).toEqual(['Datajack, in place of a vertebracopper wire 1/3 · usb c connector 0/1100', 'Sell your recipe: Datajack15']);
    expect(document.querySelector('.clinic li small')!.textContent).toBe('copper wire 1/3 · usb c connector 0/1');
    press('Enter');
    expect(sent).toEqual([]);
    press('ArrowDown');
    press('Enter');
    expect(sent).toEqual([{ type: 'sell_recipe', recipe: 'datajack' }]);
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
