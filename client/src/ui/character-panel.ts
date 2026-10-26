import type { Bionic, Body, BodyPart, Effect, Item, Player, PlayerStateMessage, Recipe } from '../net';
import { lampHere, lampOf } from '../side/lamp';
import { callCue } from './call-cue';
import { CHART, gradeOf, partDetails, pictureOf, PLACES } from './character-body';
import './character-panel.css';
import { needs, type Need } from './clinic-panel';
import { feeling } from './hunger';
import { iconUrl } from './icons';
import { level, percent, type Where } from './lamp-gauge';
import { amount } from './salvage';
import { CHARACTER_KEY } from './tuning';

const KEY = CHARACTER_KEY.toUpperCase();

export const TABS = ['Vitals', 'Body', 'Gear', 'Mind'] as const;
export type Tab = (typeof TABS)[number];

/** Head to foot. */
const PARTS: readonly (readonly [BodyPart, string])[] = [
  ['left_eye', 'Left eye'],
  ['right_eye', 'Right eye'],
  ['vertebra', 'Vertebra'],
  ['stomach', 'Stomach'],
  ['left_kidney', 'Left kidney'],
  ['right_kidney', 'Right kidney'],
  ['legs', 'Legs'],
  ['feet', 'Feet'],
];

const share = (value: number, of: number) => `${Number(((100 * value) / of).toFixed(2))}%`;

const upperFirst = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

/** "power_cell_2" is "Power cell, grade 2", as the clinic names it. */
export function bionicName(bionic: Bionic, recipes: readonly Recipe[] = []): string {
  const known = recipes.find((recipe) => recipe.bionic === bionic)?.name;
  if (known) return known;
  const [, line, grade] = /^(.*?)(?:_(\d+))?$/.exec(bionic)!;
  return upperFirst(line.replaceAll('_', ' ')) + (grade ? `, grade ${grade}` : '');
}

const runsOnPower = (body: Body): boolean => body.stomach?.startsWith('power_cell') ?? false;

export type Meter = { label: string; fill: number; good: number; text: string; note?: string };

export type Vitals = { meters: Meter[]; credits: string; effects: string[] };

/** "Rat bite, 60%, until it's treated". */
function effectLine({ kind, strength, fades }: Effect): string {
  return `${upperFirst(kind.replaceAll('_', ' '))}, ${percent(strength)}, ${fades === null ? "until it's treated" : 'fading'}`;
}

export function vitals(player: Player, where: Where = lampHere): Vitals {
  const meters: Meter[] = [];
  if (runsOnPower(player.body)) {
    const power = player.power ?? 1;
    meters.push({ label: 'Power', fill: power, good: power, text: percent(power) });
  } else {
    meters.push({
      label: 'Hunger',
      fill: player.hunger,
      good: 1 - player.hunger,
      text: percent(player.hunger),
      note: feeling(player.hunger),
    });
  }
  const health = player.health ?? 1;
  meters.push({ label: 'Health', fill: health, good: health, text: percent(health) });
  const lamp = lampOf({ type: 'player_state', player });
  if (lamp) {
    const charge = lamp.charge ?? 0;
    const state = where.plug && charge < 1 ? 'charging' : lamp.on ? 'on' : 'off';
    meters.push({ label: 'Lamp', fill: charge, good: charge, text: `${percent(charge)}, ${state}` });
  }
  return { meters, credits: amount(player.money), effects: (player.effects ?? []).map(effectLine) };
}

export type BodyRow = {
  part: BodyPart;
  label: string;
  state: 'present' | 'sold' | 'bionic';
  text: string;
  fitted?: Bionic;
};

export function bodyRows(body: Body, recipes: readonly Recipe[] = []): BodyRow[] {
  return PARTS.map(([part, label]) => {
    const fitted = body[part] ?? 'present';
    if (fitted === 'present') return { part, label, state: 'present', text: 'Your own' };
    if (fitted === 'sold') return { part, label, state: 'sold', text: 'Sold' };
    return { part, label, state: 'bionic', text: bionicName(fitted, recipes), fitted };
  });
}

export type GearRow = { name: string; count: number; weight: number; note?: string };
export type Gear = { rows: GearRow[]; load: number; limit: number };

const kg = (weight: number) => `${Number(weight.toFixed(2))} kg`;

export function gear(player: Player): Gear {
  const rows = new Map<string, GearRow>();
  for (const item of player.items) {
    const row = rows.get(item.id) ?? { name: item.name, count: 0, weight: 0, note: lampNote(item) };
    row.count += 1;
    row.weight += item.weight;
    rows.set(item.id, row);
  }
  const load = player.items.reduce((sum, { weight }) => sum + weight, 0);
  return { rows: [...rows.values()], load, limit: player.carry_limit };
}

const lampNote = ({ kind, charge }: Item) => (kind === 'lamp' ? percent(charge ?? 0) : undefined);

export type Known = {
  bionic: Bionic;
  name: string;
  needs: Need[];
  credits: number;
  short: boolean;
  replaces: string;
  after: string[];
  sold: boolean;
};

const PART_NAMES = Object.fromEntries(PARTS.map(([part, label]) => [part, label.toLowerCase()]));

export function known(player: Player, recipes: readonly Recipe[] = []): Known[] {
  const sold = new Set(player.mind?.sold ?? []);
  return (player.mind?.recipes ?? []).map((bionic) => {
    const recipe = recipes.find((each) => each.bionic === bionic);
    const needed = needs(recipe, player.items);
    const credits = recipe?.credits ?? 0;
    return {
      bionic,
      name: bionicName(bionic, recipes),
      needs: needed,
      credits,
      short: player.money < credits || needed.some(({ count, have }) => have < count),
      replaces: [...new Set((recipe?.replaces ?? []).map((part) => PART_NAMES[part]))].join(' or '),
      after: (recipe?.after ?? []).map((first) => bionicName(first, recipes)),
      sold: sold.has(bionic),
    };
  });
}

const el = <K extends keyof HTMLElementTagNameMap>(tag: K, text?: string, className?: string) => {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
};

function meter({ fill, good }: Pick<Meter, 'fill' | 'good'>): HTMLElement {
  const bar = el('span', undefined, 'character-meter');
  const inside = bar.appendChild(el('span', undefined, `lamp-level-${level(good)}`));
  inside.style.width = percent(Math.min(Math.max(fill, 0), 1));
  return bar;
}

function row(label: string, ...rest: (Node | string)[]): HTMLElement {
  const item = el('li');
  item.append(el('b', label), ...rest);
  return item;
}

/** The player's own screen, opened with C: vitals, body, gear and mind, a tab each. */
export class CharacterPanel {
  private readonly panel: HTMLElement;
  private readonly tabs: HTMLButtonElement[];
  private readonly page: HTMLElement;
  private shown = 0;
  private part = 0;
  private map?: { rows: BodyRow[]; slots: HTMLElement[]; details: HTMLElement };
  private state?: PlayerStateMessage;
  private where: Where = { dark: false, plug: false };
  private drawn = '';

  constructor(parent: HTMLElement) {
    this.panel = parent.appendChild(el('section', undefined, 'character'));
    this.panel.tabIndex = -1;
    this.panel.hidden = true;
    this.panel.ariaLabel = 'Character';
    callCue.slot(this.panel);
    const header = this.panel.appendChild(el('header'));
    header.appendChild(el('b', 'Character'));
    header.appendChild(el('span', `←→ switch · Esc or ${KEY} close`));
    const tablist = this.panel.appendChild(el('div', undefined, 'character-tabs'));
    tablist.setAttribute('role', 'tablist');
    this.tabs = TABS.map((label, i) => {
      const tab = tablist.appendChild(el('button', label));
      tab.type = 'button';
      tab.tabIndex = -1;
      tab.setAttribute('role', 'tab');
      tab.addEventListener('click', () => this.showTab(i));
      return tab;
    });
    this.page = this.panel.appendChild(el('div', undefined, 'character-page'));
    this.page.setAttribute('role', 'tabpanel');
    this.panel.addEventListener('keydown', (event) => this.onKey(event));
  }

  get isOpen(): boolean {
    return !this.panel.hidden;
  }

  get tab(): Tab {
    return TABS[this.shown];
  }

  toggle(): void {
    if (this.isOpen) this.close();
    else this.open();
  }

  open(): void {
    this.panel.hidden = false;
    this.drawn = '';
    this.render();
    this.panel.focus();
  }

  close(): void {
    if (this.panel.contains(document.activeElement)) (document.activeElement as HTMLElement).blur();
    this.panel.hidden = true;
  }

  /** Each frame: the latest `player_state`, drawn while it's open. */
  update(state: PlayerStateMessage | undefined, where: Where = lampHere): void {
    this.state = state;
    this.where = { ...where };
    if (this.isOpen) this.render();
  }

  private onKey(event: KeyboardEvent): void {
    event.stopPropagation();
    const { key } = event;
    if (key === 'Escape' || (key.toLowerCase() === CHARACTER_KEY && !event.repeat)) {
      event.preventDefault();
      this.close();
    } else if (key === 'ArrowLeft' || key === 'ArrowRight') {
      event.preventDefault();
      this.showTab((this.shown + (key === 'ArrowRight' ? 1 : -1) + TABS.length) % TABS.length);
    } else if ((key === 'ArrowUp' || key === 'ArrowDown') && this.map) {
      event.preventDefault();
      this.select((this.part + (key === 'ArrowDown' ? 1 : -1) + PARTS.length) % PARTS.length);
    }
  }

  private showTab(index: number): void {
    this.shown = index;
    this.render();
  }

  private render(): void {
    const { where } = this;
    const drawn = JSON.stringify([this.shown, this.state, where]);
    if (drawn === this.drawn) return;
    this.drawn = drawn;
    this.tabs.forEach((tab, i) => tab.setAttribute('aria-selected', String(i === this.shown)));
    this.map = undefined;
    const player = this.state?.player;
    if (!player) {
      this.page.replaceChildren(el('p', 'Not connected, so there’s nothing to show.', 'character-empty'));
      return;
    }
    const recipes = this.state?.recipes ?? [];
    const tab = this.tab;
    if (tab === 'Vitals') this.page.replaceChildren(...this.vitals(vitals(player, where)));
    else if (tab === 'Body') this.page.replaceChildren(this.body(bodyRows(player.body, recipes)));
    else if (tab === 'Gear') this.page.replaceChildren(...this.gear(gear(player)));
    else this.page.replaceChildren(...this.mind(known(player, recipes), player.money));
  }

  private vitals({ meters, credits, effects }: Vitals): HTMLElement[] {
    const list = el('ul', undefined, 'character-rows');
    for (const each of meters) {
      const item = list.appendChild(row(each.label, meter(each), el('span', each.text)));
      if (each.note) item.appendChild(el('small', each.note));
    }
    list.appendChild(row('Credits', el('span', credits)));
    const ailments = el('ul', undefined, 'character-effects');
    ailments.append(...effects.map((text) => el('li', text)));
    return [list, el('h3', 'Effects'), effects.length ? ailments : el('p', 'None.', 'character-empty')];
  }

  /** The body as a chart, each part at its place: their own organ, a stitched socket, or a bionic. */
  private body(rows: BodyRow[]): HTMLElement {
    const shown = el('div', undefined, 'character-body');
    const map = shown.appendChild(el('div', undefined, 'character-map'));
    const slots = rows.map((each, i) => {
      const { x, y, w, h, flip } = PLACES[each.part];
      const slot = map.appendChild(el('button', undefined, `character-slot character-slot-${each.state}`));
      slot.type = 'button';
      slot.tabIndex = -1;
      slot.ariaLabel = `${each.label}: ${each.text}`;
      slot.dataset.part = each.part;
      slot.dataset.picture = pictureOf(each);
      Object.assign(slot.style, {
        left: share(x - w / 2, CHART.width),
        top: share(y - h / 2, CHART.height),
        width: share(w, CHART.width),
        height: share(h, CHART.height),
      });
      const url = iconUrl(slot.dataset.picture);
      if (url) {
        const picture = slot.appendChild(el('img', undefined, flip ? 'character-flip' : undefined));
        picture.src = url;
        picture.alt = '';
      }
      const grade = gradeOf(each.fitted);
      if (grade) slot.appendChild(el('span', String(grade[0]), 'character-grade'));
      slot.addEventListener('mouseenter', () => this.select(i));
      slot.addEventListener('click', () => this.select(i));
      return slot;
    });
    this.map = { rows, slots, details: shown.appendChild(el('div', undefined, 'character-part')) };
    this.select(this.part);
    return shown;
  }

  private select(index: number): void {
    if (!this.map) return;
    this.part = index;
    const { rows, slots, details } = this.map;
    slots.forEach((slot, i) => slot.classList.toggle('character-picked', i === index));
    const { title, state, status, lines } = partDetails(rows[index]);
    details.replaceChildren(
      el('h3', title),
      el('b', status, `character-${state}`),
      ...lines.map((line) => el('p', line)),
      el('small', '↑↓ or hover for each part'),
    );
  }

  private gear({ rows, load, limit }: Gear): HTMLElement[] {
    const carrying = el('ul', undefined, 'character-rows');
    const left = 1 - load / (limit || 1);
    carrying.appendChild(row('Carrying', meter({ fill: load / (limit || 1), good: left }), el('span', `${kg(load)} of ${kg(limit)}`)));
    const list = el('ul', undefined, 'character-rows');
    for (const { name, count, weight, note } of rows) {
      const what = count > 1 ? `${name} ×${count}` : name;
      list.appendChild(row(what, el('span', note ? `${note} · ${kg(weight)}` : kg(weight))));
    }
    return [carrying, rows.length ? list : el('p', 'You carry nothing.', 'character-empty')];
  }

  private mind(recipes: Known[], money: number): HTMLElement[] {
    if (!recipes.length) return [el('p', 'You know no recipes yet.', 'character-empty')];
    const list = el('ul', undefined, 'character-recipes');
    for (const recipe of recipes) {
      const item = list.appendChild(el('li'));
      item.classList.toggle('character-short', recipe.short);
      const title = item.appendChild(el('b', recipe.name));
      if (recipe.sold) title.appendChild(el('span', 'sold to the clinic', 'character-sold-recipe'));
      const parts = item.appendChild(el('ul'));
      for (const { name, count, have } of recipe.needs) {
        parts.appendChild(el('li', `${name} ${have}/${count}`, have < count ? 'character-missing' : undefined));
      }
      if (recipe.credits) {
        const cost = parts.appendChild(el('li', `${amount(recipe.credits)} credits, you have ${amount(money)}`));
        cost.classList.toggle('character-missing', money < recipe.credits);
      }
      const where = [];
      if (recipe.replaces) where.push(`in place of your ${recipe.replaces}`);
      if (recipe.after.length) where.push(`after the ${recipe.after.join(' and ').toLowerCase()}`);
      if (where.length) item.appendChild(el('small', `${upperFirst(where.join(', '))}.`));
    }
    return [list];
  }
}
