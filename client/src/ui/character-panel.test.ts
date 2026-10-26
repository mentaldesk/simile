// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest';
import type { Item, Player, PlayerStateMessage, Recipe } from '../net';
import { bionicName, bodyRows, CharacterPanel, gear, known, TABS, vitals } from './character-panel';

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
const WIRE = item('copper_wire', 'Copper wire', 0.25);

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
    legs: 'hydraulic_legs',
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
    expect(bodyRows(STAGE_1.body).find(({ part }) => part === 'legs')?.text).toBe('Hydraulic legs');
    expect(bionicName('power_cell_2')).toBe('Power cell, grade 2');
    expect(bionicName('infrared_eye')).toBe('Infrared eye');
  });

  it('draws on the Body tab', () => {
    const { section, page } = opened();
    press(section, 'ArrowRight');
    expect(texts(section, '[aria-selected="true"]')).toEqual(['Body']);
    expect(texts(page, '.character-sold')).toEqual(['Sold']);
    expect(texts(page, '.character-bionic')).toEqual(['Power cell']);
  });
});

describe('gear', () => {
  it('lists what they carry, each kind once, against the carry limit', () => {
    expect(gear(PLAYER)).toEqual({
      rows: [
        { name: 'Lamp', count: 1, weight: 0.5, note: '60%' },
        { name: 'Copper wire', count: 2, weight: 0.5, note: undefined },
      ],
      load: 1,
      limit: 10,
    });
  });

  it('draws on the Gear tab', () => {
    const { section, page } = opened();
    press(section, 'ArrowLeft');
    press(section, 'ArrowLeft');
    expect(texts(section, '[aria-selected="true"]')).toEqual(['Gear']);
    expect(texts(page, '.character-rows > li')).toEqual(['Carrying1 kg of 10 kg', 'Lamp60% · 0.5 kg', 'Copper wire ×20.5 kg']);
  });

  it('says when they carry nothing', () => {
    const { section, page } = opened({ type: 'player_state', player: STAGE_1 });
    section.querySelectorAll<HTMLElement>('[role="tab"]')[2].click();
    expect(texts(page, '.character-empty')).toEqual(['You carry nothing.']);
  });
});

describe('mind', () => {
  it('lists each recipe they know, what it needs and what they have of it', () => {
    const [cell, datajack] = known(PLAYER, STATE.recipes);
    expect(cell).toMatchObject({ name: 'Power cell', sold: true, short: true, replaces: 'stomach', after: [] });
    expect(datajack).toEqual({
      bionic: 'datajack',
      name: 'Datajack',
      needs: [
        { name: 'copper wire', count: 3, have: 2 },
        { name: 'usb c connector', count: 1, have: 0 },
      ],
      credits: 100,
      short: true,
      replaces: 'vertebra',
      after: ['Power cell'],
      sold: false,
    });
  });

  it('knows nothing without a mind', () => {
    expect(known(STAGE_1)).toEqual([]);
  });

  it('draws on the Mind tab', () => {
    const { section, page } = opened();
    press(section, 'ArrowLeft');
    expect(texts(section, '[aria-selected="true"]')).toEqual(['Mind']);
    expect(texts(page, '.character-recipes > li > b')).toEqual(['Power cellsold to the clinic', 'Datajack']);
    const datajack = page.querySelectorAll('.character-recipes > li')[1];
    expect(texts(datajack, 'li')).toEqual(['copper wire 2/3', 'usb c connector 0/1', '100 credits, you have 120']);
    expect(texts(datajack, '.character-missing')).toEqual(['copper wire 2/3', 'usb c connector 0/1']);
    expect(datajack.querySelector('small')?.textContent).toBe('In place of your vertebra, after the power cell.');
  });

  it('says when they know none', () => {
    const { section, page } = opened({ type: 'player_state', player: STAGE_1 });
    press(section, 'ArrowLeft');
    expect(texts(page, '.character-empty')).toEqual(['You know no recipes yet.']);
  });
});

describe('CharacterPanel', () => {
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
