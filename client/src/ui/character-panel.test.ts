// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Item, Player, PlayerStateMessage, Recipe } from '../net';
import { bionicName, bodyRows, CharacterPanel, COLUMNS, gear, itemDetails, TABS, UNKNOWN_ITEM, vitals } from './character-panel';

vi.mock('./icons', () => ({ iconUrl: (id: string) => (id === 'unpainted' ? undefined : `/icons/${id}.webp`) }));

const item = (id: string, name: string, weight: number, extra: Partial<Item> = {}): Item => ({
  id,
  kind: 'part',
  name,
  weight,
  charge: null,
  on: null,
  ...extra,
});

const LAMP = item('lamp', 'Lamp', 0.5, { kind: 'lamp', charge: 0.6, on: true });
const WIRE = item('copper_wire', 'Copper wire', 0.25, { kind: 'salvage' });

const DATAJACK: Recipe = {
  bionic: 'datajack',
  name: 'Datajack',
  parts: { copper_wire: 3, usb_c_connector: 1 },
  credits: 100,
  replaces: ['vertebra'],
  after: ['power_cell'],
};
const CELL: Recipe = {
  bionic: 'power_cell',
  name: 'Power cell',
  parts: { lithium_cell: 3 },
  credits: 100,
  replaces: ['stomach'],
  after: [],
};

/** Stage 2 halfway: a kidney sold for the cell, two wires of the datajack's three. */
const PLAYER: Player = {
  money: 120,
  items: [LAMP, WIRE, WIRE],
  carry_limit: 10,
  body: {
    legs: 'present',
    vertebra: 'present',
    left_eye: 'present',
    right_eye: 'present',
    left_kidney: 'sold',
    right_kidney: 'present',
    stomach: 'power_cell',
  },
  mind: { recipes: ['power_cell', 'datajack'], sold: ['power_cell'] },
  hunger: 0.4,
  power: 0.75,
  health: 0.5,
  effects: [
    { kind: 'rat_bite', strength: 0.6, fades: null, since: '2026-01-02T10:00:00Z' },
    { kind: 'radiation', strength: 0.2, fades: 0.05, since: '2026-01-02T11:00:00Z' },
  ],
};
const STATE: PlayerStateMessage = { type: 'player_state', player: PLAYER, recipes: [CELL, DATAJACK] };

/** A stage 1 save: no stomach, feet or mind, nothing hurt. */
const STAGE_1: Player = {
  money: 0,
  items: [],
  carry_limit: 10,
  body: {
    legs: 'bionic_legs',
    vertebra: 'present',
    left_eye: 'present',
    right_eye: 'present',
    left_kidney: 'present',
    right_kidney: 'present',
  },
  hunger: 0.6,
};

const away = { dark: false, plug: false };
const texts = (root: ParentNode, selector: string) => [...root.querySelectorAll(selector)].map((element) => element.textContent);

function press(target: HTMLElement, key: string, init: KeyboardEventInit = {}): KeyboardEvent {
  const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true, ...init });
  target.dispatchEvent(event);
  return event;
}

function opened(state: PlayerStateMessage | null = STATE) {
  const root = document.body.appendChild(document.createElement('div'));
  const panel = new CharacterPanel(root);
  panel.update(state ?? undefined, away);
  panel.open();
  const section = root.querySelector<HTMLElement>('section.character')!;
  const page = section.querySelector<HTMLElement>('.character-page')!;
  return { panel, section, page };
}

afterEach(() => document.body.replaceChildren());

describe('vitals', () => {
  it('shows power in place of hunger once a cell is in the stomach, then health, the lamp, credits and effects', () => {
    const { meters, credits, effects } = vitals(PLAYER, away);
    expect(meters.map(({ label, text }) => [label, text])).toEqual([
      ['Power', '75%'],
      ['Health', '50%'],
      ['Lamp', '60%, on'],
    ]);
    expect(credits).toBe('120');
    expect(effects).toEqual(["Rat bite, 60%, until it's treated", 'Radiation, 20%, fading']);
  });

  it('shows hunger without a cell, and full health, power and no effects when left out', () => {
    const { meters, effects } = vitals(STAGE_1, away);
    expect(meters).toEqual([
      { label: 'Hunger', fill: 0.6, good: 0.4, text: '60%', note: "You're hungry." },
      { label: 'Health', fill: 1, good: 1, text: '100%' },
    ]);
    expect(effects).toEqual([]);
    const cell = vitals({ ...STAGE_1, body: { ...STAGE_1.body, stomach: 'power_cell_2' } }, away);
    expect(cell.meters[0]).toMatchObject({ label: 'Power', text: '100%' });
  });

  it('says the lamp is charging at a plug', () => {
    expect(vitals(PLAYER, { dark: false, plug: true }).meters[2].text).toBe('60%, charging');
  });

  it('draws on the Vitals tab', () => {
    const { panel, page } = opened();
    expect(panel.tab).toBe('Vitals');
    expect(texts(page, '.character-rows > li > b')).toEqual(['Power', 'Health', 'Lamp', 'Credits']);
    expect(texts(page, '.character-effects li')).toEqual(["Rat bite, 60%, until it's treated", 'Radiation, 20%, fading']);
    expect(page.querySelector<HTMLElement>('.character-meter > span')!.style.width).toBe('75%');
  });
});

describe('body', () => {
  it('lists each part head to foot: their own, sold, or the bionic in its place', () => {
    expect(bodyRows(PLAYER.body, STATE.recipes).map(({ label, state, text }) => [label, state, text])).toEqual([
      ['Left eye', 'present', 'Your own'],
      ['Right eye', 'present', 'Your own'],
      ['Vertebra', 'present', 'Your own'],
      ['Stomach', 'bionic', 'Power cell'],
      ['Left kidney', 'sold', 'Sold'],
      ['Right kidney', 'present', 'Your own'],
      ['Legs', 'present', 'Your own'],
      ['Feet', 'present', 'Your own'],
    ]);
  });

  it('names a bionic without a recipe as the clinic does', () => {
    expect(bodyRows(STAGE_1.body).find(({ part }) => part === 'legs')?.text).toBe('Bionic legs');
    expect(bionicName('power_cell_2')).toBe('Power cell, grade 2');
    expect(bionicName('infrared_eye')).toBe('Infrared eye');
  });

  it('maps each part at its place: their own organ, a stitched socket once sold, or the bionic fitted', () => {
    const { section, page } = opened();
    press(section, 'ArrowRight');
    expect(texts(section, '[aria-selected="true"]')).toEqual(['Body']);
    const slots = [...page.querySelectorAll<HTMLElement>('.character-slot')];
    expect(slots.map(({ dataset }) => [dataset.part, dataset.picture])).toEqual([
      ['left_eye', 'eye'],
      ['right_eye', 'eye'],
      ['vertebra', 'vertebra'],
      ['stomach', 'power_cell'],
      ['left_kidney', 'kidney_sold'],
      ['right_kidney', 'kidney'],
      ['legs', 'legs'],
      ['feet', 'feet'],
    ]);
    expect(slots[4].querySelector('img')?.getAttribute('src')).toBe('/icons/kidney_sold.webp');
    expect(slots[4].classList).toContain('character-slot-sold');
    expect(slots[3].classList).toContain('character-slot-bionic');
  });

  it('shows each bionic fitted, every grade of a line in its picture with its grade', () => {
    const fitted: Player = {
      ...PLAYER,
      body: {
        ...PLAYER.body,
        stomach: 'power_cell_3',
        vertebra: 'datajack',
        right_eye: 'infrared_eye',
        legs: 'bionic_legs_2',
        feet: 'spring_feet_2',
      },
    };
    const { section, page } = opened({ ...STATE, player: fitted });
    press(section, 'ArrowRight');
    const pictures = [...page.querySelectorAll<HTMLElement>('.character-slot')].map(({ dataset }) => dataset.picture);
    expect(pictures).toEqual(['eye', 'infrared_eye', 'datajack', 'power_cell', 'kidney_sold', 'kidney', 'bionic_legs', 'spring_feet']);
    expect(texts(page, '.character-grade')).toEqual(['3', '2', '2']);
  });

  it('shows a part’s details on hover, and Up and Down cycle through them head to foot', () => {
    const { section, page } = opened();
    press(section, 'ArrowRight');
    const details = () => [page.querySelector('.character-part h3')?.textContent, page.querySelector('.character-part b')?.textContent];
    expect(details()).toEqual(['Left eye', 'Your own']);
    page.querySelector('[data-part="left_kidney"]')!.dispatchEvent(new MouseEvent('mouseenter'));
    expect(details()).toEqual(['Left kidney', 'Sold']);
    expect(page.querySelector('.character-picked')?.getAttribute('data-part')).toBe('left_kidney');
    expect(press(section, 'ArrowUp').defaultPrevented).toBe(true);
    expect(details()).toEqual(['Stomach', 'Power cell']);
    expect(texts(page, '.character-part p')).toEqual([
      'A bionic in place of your stomach, grade 1 of 3.',
      expect.stringMatching(/^Runs 3 other bionics/),
    ]);
    press(section, 'ArrowDown');
    press(section, 'ArrowDown');
    press(section, 'ArrowDown');
    press(section, 'ArrowDown');
    expect(details()).toEqual(['Feet', 'Your own']);
    press(section, 'ArrowDown');
    expect(details()).toEqual(['Left eye', 'Your own']);
    press(section, 'ArrowRight');
    expect(texts(section, '[aria-selected="true"]')).toEqual(['Gear']);
  });

  it('keeps the part picked as each player_state redraws it', () => {
    const { panel, section, page } = opened();
    press(section, 'ArrowRight');
    press(section, 'ArrowUp');
    panel.update({ ...STATE, player: { ...PLAYER, body: { ...PLAYER.body, feet: 'spring_feet' } } }, away);
    expect(page.querySelector('.character-part b')?.textContent).toBe('Spring feet');
  });

  it('maps a stage 1 player, with no stomach or feet in their save', () => {
    const { section, page } = opened({ type: 'player_state', player: STAGE_1 });
    press(section, 'ArrowRight');
    const slots = [...page.querySelectorAll<HTMLElement>('.character-slot')];
    expect(slots.map(({ dataset }) => dataset.picture)).toEqual([
      'eye',
      'eye',
      'vertebra',
      'stomach',
      'kidney',
      'kidney',
      'bionic_legs',
      'feet',
    ]);
    page.querySelector('[data-part="legs"]')!.dispatchEvent(new MouseEvent('mouseenter'));
    expect(texts(page, '.character-part p')).toEqual(['A bionic in place of your legs, grade 1 of 3.', 'Run faster and jump further.']);
  });
});

describe('gear', () => {
  const RATIONS = item('ration_pack', 'Ration pack', 0.5, { kind: 'food' });
  const CELLS = item('lithium_cell', 'Lithium cell', 0.3);
  const ODD = item('unpainted', 'Odd thing', 1, { kind: 'salvage' });
  const LADEN: Player = {
    ...PLAYER,
    items: [
      LAMP,
      WIRE,
      RATIONS,
      WIRE,
      CELLS,
      CELLS,
      CELLS,
      item('usb_c_connector', 'USB-C connector', 0.1),
      item('scrap_steel', 'Scrap steel', 4.5, { kind: 'salvage' }),
      item('apex_actuator', 'Apex actuator', 2),
      ODD,
    ],
  };
  const LADEN_STATE: PlayerStateMessage = { ...STATE, player: LADEN };

  function onGear(state: PlayerStateMessage = LADEN_STATE) {
    const shown = opened(state);
    shown.section.querySelectorAll<HTMLElement>('[role="tab"]')[2].click();
    return shown;
  }

  const tiles = (page: HTMLElement) => [...page.querySelectorAll<HTMLElement>('.character-tile')];
  const picked = (page: HTMLElement) => page.querySelector<HTMLElement>('.character-tile.character-picked')?.dataset.item;
  const details = (page: HTMLElement) => texts(page, '.character-item > :is(h3, b, p)');

  it('has a tile per kind of item in the order they got it, with its count, weight and picture', () => {
    const { tiles, load, limit } = gear(LADEN);
    expect(tiles.map(({ id, count, weight }) => [id, count, Number(weight.toFixed(2))])).toEqual([
      ['lamp', 1, 0.5],
      ['copper_wire', 2, 0.5],
      ['ration_pack', 1, 0.5],
      ['lithium_cell', 3, 0.9],
      ['usb_c_connector', 1, 0.1],
      ['scrap_steel', 1, 4.5],
      ['apex_actuator', 1, 2],
      ['unpainted', 1, 1],
    ]);
    expect(tiles[0]).toMatchObject({ kind: 'lamp', picture: 'lamp', charge: 0.6, on: true });
    expect(tiles[1]).not.toHaveProperty('charge');
    expect(Number(load.toFixed(2))).toBe(10);
    expect(limit).toBe(10);
  });

  it('shows the fallback picture for an item with none of its own', () => {
    expect(gear(LADEN).tiles.at(-1)?.picture).toBe(UNKNOWN_ITEM);
    const { page } = onGear();
    expect(tiles(page).at(-1)?.querySelector('img')?.getAttribute('src')).toBe(`/icons/${UNKNOWN_ITEM}.webp`);
  });

  it('details what each is for, its weight, the lamp’s charge, and the known recipes that use it', () => {
    const [lamp, wire, rations, cells, usb, scrap] = gear(LADEN).tiles;
    const detail = (tile: (typeof lamp)) => itemDetails(tile, LADEN, STATE.recipes);
    expect(detail(lamp)).toEqual({
      title: 'Lamp',
      kind: 'lamp',
      status: 'Your lamp, to see by',
      lines: ['0.5 kg.', 'Charged 60%, on. L switches it.'],
    });
    expect(detail(wire).lines).toEqual(['2 of them, 0.25 kg each, 0.5 kg in all.', 'Your recipe for the datajack uses it.']);
    expect(detail(rations)).toMatchObject({ status: 'Food, to eat', lines: ['0.5 kg.', "F eats it once you're peckish."] });
    expect(detail(cells)).toMatchObject({
      status: 'A part, for a bionic',
      lines: ['3 of them, 0.3 kg each, 0.9 kg in all.', 'Your recipe for the power cell uses it.'],
    });
    expect(detail(usb).lines.at(-1)).toBe('Your recipe for the datajack uses it.');
    expect(itemDetails(usb, { ...LADEN, mind: { recipes: [], sold: [] } }, STATE.recipes).lines.at(-1)).toBe('No recipe you know uses it.');
    expect(detail(scrap)).toMatchObject({ status: 'Salvage, to sell', lines: ['4.5 kg.'] });
    const both: Recipe = { ...DATAJACK, bionic: 'infrared_eye', name: 'Infrared eye' };
    const knowing: Player = { ...LADEN, mind: { recipes: ['datajack', 'infrared_eye'], sold: [] } };
    expect(itemDetails(wire, knowing, [DATAJACK, both]).lines.at(-1)).toBe('Your recipe for the datajack and the infrared eye uses it.');
  });

  it('draws a grid of pictures, each with its count when there’s more than one and its name, under the load', () => {
    const { section, page } = onGear();
    expect(texts(section, '[aria-selected="true"]')).toEqual(['Gear']);
    expect(texts(page, '.character-rows > li')).toEqual(['Carrying10 kg of 10 kg']);
    expect(page.querySelector<HTMLElement>('.character-grid')!.style.getPropertyValue('--columns')).toBe(String(COLUMNS));
    expect(tiles(page).map(({ dataset }) => dataset.item)).toEqual(gear(LADEN).tiles.map(({ id }) => id));
    expect(tiles(page)[1].querySelector('img')?.getAttribute('src')).toBe('/icons/copper_wire.webp');
    expect(texts(page, '.character-count')).toEqual(['×2', '×3']);
    expect(texts(page, '.character-tile-name').slice(0, 3)).toEqual(['Lamp', 'Copper wire', 'Ration pack']);
    expect(tiles(page)[0].querySelector<HTMLElement>('.character-meter > span')!.style.width).toBe('60%');
  });

  it('shows a tile’s details on hover, and lets go when the mouse leaves the grid', () => {
    const { section, page } = onGear();
    expect(picked(page)).toBeUndefined();
    tiles(page)[1].dispatchEvent(new MouseEvent('mouseenter'));
    expect(picked(page)).toBe('copper_wire');
    expect(details(page)).toEqual([
      'Copper wire',
      'Salvage, to sell',
      '2 of them, 0.25 kg each, 0.5 kg in all.',
      'Your recipe for the datajack uses it.',
    ]);
    page.querySelector('.character-grid')!.dispatchEvent(new MouseEvent('mouseleave'));
    expect(picked(page)).toBeUndefined();
    expect(page.querySelector('.character-item h3')).toBeNull();
    press(section, 'ArrowRight');
    expect(texts(section, '[aria-selected="true"]')).toEqual(['Vitals']);
  });

  it('picks the first tile on Down, moves with the arrows, and lets go Up off the top row so ← → switch tabs', () => {
    const { section, page } = onGear();
    expect(press(section, 'ArrowDown').defaultPrevented).toBe(true);
    expect(picked(page)).toBe('lamp');
    press(section, 'ArrowRight');
    expect(picked(page)).toBe('copper_wire');
    expect(texts(section, '[aria-selected="true"]')).toEqual(['Gear']);
    press(section, 'ArrowDown');
    expect(picked(page)).toBe('apex_actuator');
    press(section, 'ArrowDown');
    expect(picked(page)).toBe('apex_actuator');
    press(section, 'ArrowRight');
    press(section, 'ArrowRight');
    expect(picked(page)).toBe('unpainted');
    expect(details(page)[0]).toBe('Odd thing');
    press(section, 'ArrowLeft');
    press(section, 'ArrowUp');
    expect(picked(page)).toBe('copper_wire');
    press(section, 'ArrowLeft');
    press(section, 'ArrowLeft');
    expect(picked(page)).toBe('lamp');
    press(section, 'ArrowUp');
    expect(picked(page)).toBeUndefined();
    press(section, 'ArrowLeft');
    expect(texts(section, '[aria-selected="true"]')).toEqual(['Body']);
  });

  it('keeps the tile picked as each player_state redraws it, or the one in its place once it’s gone', () => {
    const { panel, section, page } = onGear();
    press(section, 'ArrowDown');
    press(section, 'ArrowRight');
    panel.update({ ...LADEN_STATE, player: { ...LADEN, items: [...LADEN.items, WIRE] } }, away);
    expect(picked(page)).toBe('copper_wire');
    expect(details(page)[2]).toBe('3 of them, 0.25 kg each, 0.75 kg in all.');
    panel.update({ ...LADEN_STATE, player: { ...LADEN, items: LADEN.items.filter(({ id }) => id !== 'copper_wire') } }, away);
    expect(picked(page)).toBe('ration_pack');
  });

  it('starts with nothing picked each time it’s shown', () => {
    const { section, page } = onGear();
    press(section, 'ArrowDown');
    section.querySelectorAll<HTMLElement>('[role="tab"]')[1].click();
    section.querySelectorAll<HTMLElement>('[role="tab"]')[2].click();
    expect(picked(page)).toBeUndefined();
  });

  it('lets go of the tile picked when the Gear tab is clicked again', () => {
    const { section, page } = onGear();
    press(section, 'ArrowDown');
    section.querySelectorAll<HTMLElement>('[role="tab"]')[2].click();
    expect(picked(page)).toBeUndefined();
    expect(page.querySelector('.character-item h3')).toBeNull();
    press(section, 'ArrowRight');
    expect(texts(section, '[aria-selected="true"]')).toEqual(['Vitals']);
  });

  it('opens again with nothing picked, so ← → switch tabs straight away', () => {
    const { panel, section, page } = onGear();
    press(section, 'ArrowDown');
    panel.close();
    panel.open();
    expect(picked(page)).toBeUndefined();
    press(section, 'ArrowRight');
    expect(texts(section, '[aria-selected="true"]')).toEqual(['Vitals']);
  });

  it('says when they carry nothing', () => {
    const { section, page } = opened({ type: 'player_state', player: STAGE_1 });
    section.querySelectorAll<HTMLElement>('[role="tab"]')[2].click();
    expect(texts(page, '.character-empty')).toEqual(['You carry nothing.']);
  });
});

describe('CharacterPanel', () => {
  it('has a tab each for vitals, body and gear, and none for recipes', () => {
    const { section } = opened();
    expect(texts(section, '[role="tab"]')).toEqual(['Vitals', 'Body', 'Gear']);
  });

  it('opens on the tab it was left on, keeps its keys from the game, and closes on Esc or C', () => {
    const { panel, section } = opened();
    let reached = 0;
    const onWindow = () => reached++;
    window.addEventListener('keydown', onWindow);
    expect(document.activeElement).toBe(section);
    expect(press(section, 'ArrowRight').defaultPrevented).toBe(true);
    press(section, 'Escape');
    expect(panel.isOpen).toBe(false);
    panel.toggle();
    expect(panel.tab).toBe(TABS[1]);
    press(section, 'c');
    expect(panel.isOpen).toBe(false);
    expect(reached).toBe(0);
    window.removeEventListener('keydown', onWindow);
  });

  it('redraws from each player_state while open', () => {
    const { panel, page } = opened();
    panel.update({ ...STATE, player: { ...PLAYER, health: 0.25 } }, away);
    expect(page.querySelectorAll('.character-rows > li')[1].textContent).toBe('Health25%');
  });

  it('says there is nothing to show before the first player_state', () => {
    const { page } = opened(null);
    expect(page.textContent).toMatch(/Not connected/);
  });
});
