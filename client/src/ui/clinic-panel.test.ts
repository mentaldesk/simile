// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Buyer, ClientMessage, Fitting, Item, Player, Recipe } from '../net';
import { ClinicPanel, columns, deals, details, iconOf, needed, needs, note, sideOf, type Side } from './clinic-panel';
import { iconUrl } from './icons';

vi.mock('./icons', async () => {
  const { icons } = (await import('../../../content/icons/icons.json')).default;
  return { iconUrl: (id: string) => (id in icons ? `/icons/${id}.webp` : undefined) };
});

const WIRE: Item = { id: 'copper_wire', kind: 'salvage', name: 'Copper wire', weight: 1.5, charge: null, on: null };
const LEGS: Fitting = { bionic: 'bionic_legs', name: 'Bionic legs', price: 80, parts: ['legs'] };
const EYE: Fitting = { bionic: 'infrared_eye', name: 'Infrared eye', price: 200, parts: ['left_eye', 'right_eye'] };
const JACK: Fitting = { bionic: 'datajack', name: 'Datajack', price: 100, parts: ['vertebra'] };
const FIRST = 'Needs a power cell first.';
const WAITING: Fitting = { ...JACK, blocked: FIRST };
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
const PLUG: Item = { id: 'usb_c_connector', kind: 'part', name: 'USB-C connector', weight: 0.1, charge: null, on: null };
const LENS: Item = { id: 'infrared_lens', kind: 'part', name: 'Infrared lens', weight: 0.2, charge: null, on: null };
const LAMP: Item = { id: 'lamp', kind: 'lamp', name: 'Lamp', weight: 1, charge: 0.4, on: false };
const TRADER: Buyer = {
  place: 'scrap_stall',
  name: "The scrap trader's stall",
  prices: {},
  stock: [
    { item: PLUG, price: 10 },
    { item: LENS, price: 80 },
    { item: PLUG, price: 24 },
  ],
};
const SELLS: Buyer = { place: 'scrap_stall', name: "The scrap trader's stall", prices: { copper_wire: 6, usb_c_connector: 12 } };

describe('deals', () => {
  it('lists talking, the salvage, the kidney and each fitting in each part it takes', () => {
    expect(deals(CLINIC, player(90, [WIRE, WIRE]), DOCTOR)).toEqual([
      { kind: 'talk', name: 'Talk to Annelie Joubert', label: 'Talk to Annelie Joubert', npcId: 'annelie' },
      { kind: 'sell', name: 'Everything', label: 'Sell everything: copper wire ×2', price: 12 },
      { kind: 'item', name: 'Copper wire', label: 'Sell one: Copper wire', price: 6, item: 'copper_wire', count: 2 },
      { kind: 'part', name: 'A kidney', label: 'Sell a kidney', price: 100, part: 'left_kidney' },
      { kind: 'fit', name: 'Bionic legs', label: 'Bionic legs, in place of your legs', price: 80, bionic: 'bionic_legs', part: 'legs', needs: [], short: false },
      { kind: 'fit', name: 'Infrared eye, left eye', label: 'Infrared eye, in place of your left eye', price: 200, bionic: 'infrared_eye', part: 'left_eye', needs: [], short: true },
      { kind: 'fit', name: 'Infrared eye, right eye', label: 'Infrared eye, in place of your right eye', price: 200, bionic: 'infrared_eye', part: 'right_eye', needs: [], short: true },
    ]);
  });

  it('says what each fitting from a recipe uses up, what they have of it, and the recipes she buys', () => {
    const buyer: Buyer = { ...CLINIC, parts: undefined, fittings: [JACK], recipes: { datajack: 15 } };
    const found = deals(buyer, player(500, [WIRE, WIRE]), undefined, [CELL_RECIPE, JACK_RECIPE]);

    expect(found).toEqual([
      { kind: 'sell', name: 'Everything', label: 'Sell everything: copper wire ×2', price: 12 },
      { kind: 'item', name: 'Copper wire', label: 'Sell one: Copper wire', price: 6, item: 'copper_wire', count: 2 },
      {
        kind: 'fit',
        name: 'Datajack',
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
      { kind: 'recipe', name: 'Datajack recipe', label: 'Sell your recipe: Datajack', price: 15, bionic: 'datajack' },
    ]);
    expect(needed(needs(JACK_RECIPE, [WIRE]))).toBe('copper wire 1/3 · usb c connector 0/1');
  });

  it('is short of nothing once they have the parts and the credits', () => {
    const connector: Item = { id: 'usb_c_connector', kind: 'part', name: 'USB-C connector', weight: 0.1, charge: null, on: null };
    const [fit] = deals({ ...CLINIC, prices: {}, parts: undefined, fittings: [JACK] }, player(100, [WIRE, WIRE, WIRE, connector]), undefined, [JACK_RECIPE]);

    expect(fit).toMatchObject({ kind: 'fit', short: false, needs: [{ have: 3 }, { name: 'usb-c connector', have: 1 }] });
  });

  it('says why a fitting is blocked, apart from what it is short of', () => {
    const [jack] = deals({ ...CLINIC, prices: {}, parts: undefined, fittings: [WAITING] }, player(0), undefined, [JACK_RECIPE]);

    expect(jack).toMatchObject({ kind: 'fit', bionic: 'datajack', short: true, blocked: FIRST });
    expect(note(jack, false, 0)).toBe(FIRST);
    expect(deals({ ...CLINIC, fittings: [JACK] }, player(0))[1]).not.toHaveProperty('blocked');
  });

  it('leaves out what the doctor no longer buys or fits, and talking with nobody to talk to', () => {
    expect(deals({ ...CLINIC, parts: undefined, fittings: [EYE] }, player(0))).toHaveLength(2);
  });
});

describe('selling', () => {
  it('lists everything it buys as one row, then each kind with its price and how many they have', () => {
    expect(deals(SELLS, player(0, [WIRE, PLUG, WIRE, LENS]))).toEqual([
      { kind: 'sell', name: 'Everything', label: 'Sell everything: copper wire ×2 and USB-C connector', price: 24 },
      { kind: 'item', name: 'Copper wire', label: 'Sell one: Copper wire', price: 6, item: 'copper_wire', count: 2 },
      { kind: 'item', name: 'USB-C connector', label: 'Sell one: USB-C connector', price: 12, item: 'usb_c_connector', count: 1 },
    ]);
  });

  it('sells the lamp only on its own, and buys it back at what the stall asks', () => {
    const buyer = { ...SELLS, prices: { ...SELLS.prices, lamp: 12 } };
    expect(deals(buyer, player(0, [LAMP, WIRE, PLUG]))).toEqual([
      { kind: 'sell', name: 'Everything', label: 'Sell everything: copper wire and USB-C connector', price: 18 },
      { kind: 'item', name: 'Lamp', label: 'Sell one: Lamp', price: 12, item: 'lamp', count: 1 },
      { kind: 'item', name: 'Copper wire', label: 'Sell one: Copper wire', price: 6, item: 'copper_wire', count: 1 },
      { kind: 'item', name: 'USB-C connector', label: 'Sell one: USB-C connector', price: 12, item: 'usb_c_connector', count: 1 },
    ]);
    expect(deals(buyer, player(0, [LAMP, WIRE])).map(({ kind }) => kind)).toEqual(['item', 'item']);
    const stall: Buyer = { ...SELLS, prices: {}, stock: [{ item: LAMP, price: 24 }] };
    expect(deals(stall, player(30))).toEqual([{ kind: 'buy', name: 'Lamp', label: 'Buy back: Lamp', price: 24, item: 'lamp', count: 1, weight: 1 }]);
  });
});

describe('buying back', () => {
  it('offers each part once, at the cheapest, with how many there are', () => {
    expect(deals(TRADER, player(50))).toEqual([
      { kind: 'buy', name: 'USB-C connector', label: 'Buy back: USB-C connector ×2', price: 10, item: 'usb_c_connector', count: 2, weight: 0.1 },
      { kind: 'buy', name: 'Infrared lens', label: 'Buy back: Infrared lens', price: 80, item: 'infrared_lens', count: 1, weight: 0.2, short: 'money' },
    ]);
  });

  it('says what a part costs against what they have, or that it will not fit', () => {
    const [plug, lens] = deals(TRADER, player(50));
    const [heavy] = deals(TRADER, player(50, [{ ...WIRE, weight: 9.95 }]));

    expect(note(plug, false, 50)).toBe('Enter to buy it back.');
    expect(note(lens, false, 50)).toBe('It costs 80, and you have 50.');
    expect(note(heavy, false, 50)).toBe('It weighs 0.1 kg, more than you can carry now.');
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

    expect(patch).toEqual({ kind: 'treat', name: 'Patch up', label: 'Patch up', price: 15, effect: null, short: false });
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

describe('columns', () => {
  it('puts what they would take from you on the left, and what they offer on the right', () => {
    const buyer: Buyer = { ...TREATED, fittings: [LEGS], recipes: { datajack: 15 }, stock: [{ item: LENS, price: 80 }] };
    const { yours, theirs } = columns(deals(buyer, player(90, [WIRE, WIRE]), DOCTOR, [JACK_RECIPE]));

    expect(yours.map(({ name }) => name)).toEqual(['Everything', 'Copper wire', 'A kidney', 'Datajack recipe']);
    expect(theirs.map(({ name }) => name)).toEqual(['Talk to Annelie Joubert', 'Patch up', 'Treat the infection', 'Infrared lens', 'Bionic legs']);
    expect(sideOf(yours[0]!)).toBe('yours');
    expect(sideOf(theirs[0]!)).toBe('theirs');
  });
});

describe('iconOf', () => {
  it('draws items by their id, parts as the organ, fittings by their line and recipes as a schematic', () => {
    const buyer: Buyer = { ...TREATED, fittings: [{ ...LEGS, bionic: 'bionic_legs_2' }, EYE], recipes: { datajack: 15 } };
    const icons = deals(buyer, player(90, [WIRE, WIRE]), DOCTOR).map(iconOf);

    expect(icons).toEqual(['talk', 'patch_up', 'treat_infection', 'sell_everything', 'copper_wire', 'kidney', 'bionic_legs', 'infrared_eye', 'infrared_eye', 'schematic']);
    expect(['copper_wire', 'kidney', 'bionic_legs', 'infrared_eye', 'schematic', 'lamp'].every((id) => iconUrl(id))).toBe(true);
  });
});

describe('details', () => {
  it('says what a deal pays or costs against what they have, what a fitting uses up, or why it waits', () => {
    const stock = [
      { item: PLUG, price: 10 },
      { item: PLUG, price: 10 },
    ];
    const buyer: Buyer = { ...CLINIC, prices: { copper_wire: 6 }, fittings: [JACK, WAITING], stock };
    const [item, buy, kidney, jack, waiting] = deals(buyer, player(50, [WIRE, WIRE]), undefined, [JACK_RECIPE]).slice(1);

    expect(details(item!, 50)).toEqual(['Pays 6 each', 'You have 2']);
    expect(details(buy!, 50)).toEqual(['Costs 10 of your 50', 'Weighs 0.1 kg · 2 for sale']);
    expect(details(kidney!, 50)).toEqual(['Pays 100']);
    expect(details(jack!, 50)).toEqual(['Costs 100 of your 50', 'copper wire 2/3 · usb c connector 0/1']);
    expect(details(waiting!, 50)).toEqual([FIRST]);
  });
});

describe('ClinicPanel', () => {
  let sent: ClientMessage[];
  let talk: ReturnType<typeof vi.fn<(npcId: string) => void>>;
  let panel: ClinicPanel;

  const section = () => document.querySelector<HTMLElement>('.clinic')!;
  const rows = (side: Side) => [...document.querySelectorAll(`.clinic-${side} li`)].map((li) => li.querySelector('.clinic-name')!.textContent);
  const selected = () => document.querySelector('.clinic-selected .clinic-name')?.textContent;
  const chosen = () => document.querySelector('.clinic-chosen')!.textContent;
  const status = () => document.querySelector('.clinic footer p')!.textContent;
  const press = (...keys: string[]) => {
    for (const key of keys) {
      (document.activeElement ?? section()).dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true }));
    }
  };

  beforeEach(() => {
    sent = [];
    talk = vi.fn<(npcId: string) => void>();
    panel = new ClinicPanel(document.body, (message) => sent.push(message) > 0, talk);
  });

  afterEach(() => document.body.replaceChildren());

  it('opens on yours and theirs side by side, with their credits at the top and an icon for each', () => {
    panel.open(CLINIC, player(90, [WIRE]), DOCTOR);

    expect(panel.isOpen).toBe(true);
    expect(document.activeElement).toBe(section());
    expect(section().querySelector('header b')!.textContent).toBe('The Clinic');
    expect(section().querySelector('header .clinic-money')!.textContent).toBe('Credits 90');
    expect(rows('yours')).toEqual(['Copper wire', 'A kidney']);
    expect(rows('theirs')).toEqual(['Talk to Annelie Joubert', 'Bionic legs', 'Infrared eye, left eye', 'Infrared eye, right eye']);
    expect(selected()).toBe('Copper wire');
    expect(chosen()).toBe('Sell one: Copper wirePays 6');
    expect(document.querySelector('.clinic-yours li .clinic-icon img')).not.toBeNull();
    expect(document.querySelector('.clinic-theirs li .clinic-icon')!.classList.contains('clinic-blank')).toBe(true);
  });

  it('moves between the columns on ← and →, and within one on ↑ and ↓, past talking first', () => {
    panel.open(CLINIC, player(90, [WIRE]), DOCTOR);
    press('ArrowRight');
    expect(selected()).toBe('Bionic legs');
    expect(document.querySelector('.clinic-active h3')!.textContent).toBe('Theirs');
    expect(document.querySelector('.clinic-kept .clinic-name')!.textContent).toBe('Copper wire');
    press('ArrowUp');
    expect(selected()).toBe('Talk to Annelie Joubert');
    press('ArrowUp');
    expect(selected()).toBe('Infrared eye, right eye');
    press('ArrowLeft', 'ArrowDown');
    expect(selected()).toBe('A kidney');
    press('ArrowRight');
    expect(selected()).toBe('Infrared eye, right eye');
  });

  it('opens on theirs when it buys nothing they carry, and says so', () => {
    panel.open(TRADER, player(50));

    expect(selected()).toBe('USB-C connector');
    expect(document.querySelector('.clinic-yours ol')!.getAttribute('data-empty')).toBe('Nothing they want.');
    press('ArrowLeft');
    expect(selected()).toBe('USB-C connector');
  });

  it('sells a kidney only on a second Enter', () => {
    panel.open(CLINIC, player(0));
    press('Enter');

    expect(sent).toEqual([]);
    expect(status()).toBe("Enter again to sell a kidney for 100. It can't be undone.");
    expect(section().querySelector('.clinic-armed .clinic-name')!.textContent).toBe('A kidney');
    press('Enter');
    expect(sent).toEqual([{ type: 'sell_part', part: 'left_kidney' }]);
  });

  it('forgets the first Enter when the choice moves to the other column and back', () => {
    panel.open(CLINIC, player(90));
    press('Enter', 'ArrowRight', 'ArrowLeft', 'Enter');

    expect(sent).toEqual([]);
  });

  it('treats them on one Enter, and never for what they cannot pay', () => {
    panel.open(TREATED, player(20));
    press('ArrowRight', 'Enter', 'ArrowDown', 'Enter');

    expect(sent).toEqual([{ type: 'treat', effect: null }]);
    expect(section().querySelector('.clinic-short .clinic-name')!.textContent).toBe('Treat the infection');
  });

  it('fits the legs on a second Enter, and never what they cannot pay for', () => {
    panel.open(CLINIC, player(90));
    press('ArrowRight', 'Enter');
    expect(status()).toBe("Enter again to have this fitted in place of your legs for 80. It can't be undone.");
    press('Enter', 'ArrowDown', 'Enter', 'Enter');

    expect(sent).toEqual([{ type: 'fit', bionic: 'bionic_legs', part: 'legs' }]);
    expect(status()).toBe('It costs 200, and you have 90.');
    expect(chosen()).toBe('Infrared eye, in place of your left eyeCosts 200 of your 90');
  });

  it('sells the salvage at once, and talks to the doctor by closing', () => {
    panel.open(CLINIC, player(0, [WIRE]), DOCTOR);
    press('Enter');
    expect(sent).toEqual([{ type: 'sell', item: 'copper_wire' }]);

    press('ArrowRight', 'ArrowUp', 'Enter');
    expect(talk).toHaveBeenCalledWith('annelie');
    expect(panel.isOpen).toBe(false);
  });

  it('keeps the choice as the offers change, and closes when there is no buyer', () => {
    panel.open(CLINIC, player(100));
    press('ArrowRight', 'ArrowDown');
    panel.update({ ...CLINIC, fittings: [EYE] }, player(100));

    expect(selected()).toBe('Infrared eye, left eye');
    panel.update(undefined, player(100));
    expect(panel.isOpen).toBe(false);
  });

  it('stays in its column once it empties, and chooses past talking on →', () => {
    panel.open(CLINIC, player(0), DOCTOR);
    panel.update({ ...CLINIC, parts: undefined }, player(100), DOCTOR);

    expect(selected()).toBeUndefined();
    expect(document.querySelector('.clinic-active h3')!.textContent).toBe('Yours');
    press('Enter');
    expect(talk).not.toHaveBeenCalled();
    press('ArrowRight');
    expect(selected()).toBe('Bionic legs');
  });

  it('waits for the arrows once everything is sold, never selling the lamp on a quick second Enter', () => {
    const stall = { ...SELLS, prices: { ...SELLS.prices, lamp: 12 } };
    panel.open(stall, player(0, [LAMP, WIRE, PLUG]));
    press('Enter');
    panel.update(stall, player(18, [LAMP]));

    expect(rows('yours')).toEqual(['Lamp']);
    expect(selected()).toBeUndefined();
    expect(status()).toBe('Done. Choose the next with the arrows.');
    press('Enter');
    expect(sent).toEqual([{ type: 'sell', item: null }]);
    press('ArrowDown');
    expect(selected()).toBe('Lamp');
    press('Enter');
    expect(sent).toEqual([
      { type: 'sell', item: null },
      { type: 'sell', item: 'lamp' },
    ]);
  });

  it('never buys back what they just sold on a quick second Enter', () => {
    panel.open(SELLS, player(0, [PLUG]));
    press('Enter');
    panel.update({ ...SELLS, stock: [{ item: PLUG, price: 24 }] }, player(12));

    expect(rows('theirs')).toEqual(['USB-C connector']);
    expect(selected()).toBeUndefined();
    press('Enter');
    expect(sent).toEqual([{ type: 'sell', item: 'usb_c_connector' }]);
    press('ArrowRight');
    expect(selected()).toBe('USB-C connector');
  });

  it('lands off the lamp once the chosen row is sold', () => {
    const stall = { ...SELLS, prices: { ...SELLS.prices, lamp: 12 } };
    panel.open(stall, player(0, [WIRE, PLUG, LAMP]));
    press('ArrowDown', 'ArrowDown', 'Enter');
    panel.update(stall, player(12, [WIRE, LAMP]));

    expect(rows('yours')).toEqual(['Copper wire', 'Lamp']);
    press('ArrowDown');
    expect(selected()).toBe('Copper wire');
  });

  it('shows what a fitting needs when chosen, and sells a recipe on one Enter', () => {
    const buyer: Buyer = { ...CLINIC, prices: {}, parts: undefined, fittings: [JACK], recipes: { datajack: 15 } };
    panel.open(buyer, player(500, [WIRE]), undefined, [JACK_RECIPE]);

    expect(rows('yours')).toEqual(['Datajack recipe']);
    expect(rows('theirs')).toEqual(['Datajack']);
    press('ArrowRight');
    expect(chosen()).toBe('Datajack, in place of a vertebraCosts 100 of your 500copper wire 1/3 · usb c connector 0/1');
    press('Enter');
    expect(sent).toEqual([]);
    press('ArrowLeft', 'Enter');
    expect(sent).toEqual([{ type: 'sell_recipe', recipe: 'datajack' }]);
  });

  it('dims a blocked fitting with its reason in place of its price, and never fits it', () => {
    const buyer: Buyer = { ...CLINIC, prices: {}, parts: undefined, fittings: [WAITING, LEGS] };
    panel.open(buyer, player(500, [WIRE]), undefined, [JACK_RECIPE]);

    const [jack, legs] = document.querySelectorAll('.clinic-theirs li');
    expect(jack!.textContent).toBe(`Datajack${FIRST}`);
    expect(jack!.classList.contains('clinic-blocked')).toBe(true);
    expect(legs!.classList.contains('clinic-blocked')).toBe(false);
    expect(legs!.querySelector('b')!.textContent).toBe('80');
    expect(status()).toBe(FIRST);
    expect(document.querySelector('.clinic-chosen .clinic-reason')!.textContent).toBe(FIRST);
    press('Enter', 'Enter');
    expect(sent).toEqual([]);
    press('ArrowDown', 'Enter', 'Enter');
    expect(sent).toEqual([{ type: 'fit', bionic: 'bionic_legs', part: 'legs' }]);
  });

  it('buys a part back on one Enter, and never one they cannot pay for', () => {
    panel.open(TRADER, player(50));

    expect(section().querySelector('header b')!.textContent).toBe("The scrap trader's stall");
    expect(section().ariaLabel).toBe("The scrap trader's stall");
    expect(rows('theirs')).toEqual(['USB-C connector', 'Infrared lens']);
    expect(document.querySelector('.clinic-theirs .clinic-count')!.textContent).toBe('×2');
    expect(section().querySelectorAll('.clinic-short')).toHaveLength(1);
    press('Enter', 'ArrowDown', 'Enter');
    expect(sent).toEqual([{ type: 'buy', item: 'usb_c_connector' }]);
  });

  it('sells one of a kind a press, keeping the choice while they have more', () => {
    panel.open(SELLS, player(0, [WIRE, PLUG, WIRE]));
    expect(rows('yours')).toEqual(['Everything', 'Copper wire', 'USB-C connector']);
    press('ArrowDown');
    expect(status()).toBe('Enter to sell one.');
    press('Enter');
    panel.update(SELLS, player(6, [PLUG, WIRE]));
    expect(selected()).toBe('Copper wire');
    press('Enter');
    panel.update(SELLS, player(12, [PLUG]));
    expect(rows('yours')).toEqual(['USB-C connector']);
    press('Enter');
    expect(sent).toHaveLength(2);
    press('ArrowDown', 'Enter');
    expect(sent).toEqual([
      { type: 'sell', item: 'copper_wire' },
      { type: 'sell', item: 'copper_wire' },
      { type: 'sell', item: 'usb_c_connector' },
    ]);
  });

  it('sells everything on one Enter, and the lamp only on its own', () => {
    panel.open({ ...SELLS, prices: { ...SELLS.prices, lamp: 12 } }, player(0, [LAMP, WIRE, PLUG]));
    expect(rows('yours')).toEqual(['Everything', 'Lamp', 'Copper wire', 'USB-C connector']);
    press('Enter', 'ArrowDown', 'Enter');
    expect(sent).toEqual([
      { type: 'sell', item: null },
      { type: 'sell', item: 'lamp' },
    ]);
  });

  it('closes on Esc or E, and a click chooses and acts', () => {
    panel.open(CLINIC, player(0));
    press('e');
    expect(panel.isOpen).toBe(false);

    panel.open(CLINIC, player(100));
    const legs = () => document.querySelectorAll<HTMLElement>('.clinic-theirs li')[0]!;
    legs().click();
    expect(selected()).toBe('Bionic legs');
    legs().click();
    expect(sent).toEqual([{ type: 'fit', bionic: 'bionic_legs', part: 'legs' }]);
    press('Escape');
    expect(panel.isOpen).toBe(false);
  });
});

