import type { Bionic, BodyPart, Buyer, ClientMessage, EffectKind, Item, Player, Recipe } from '../net';
import { callCue } from './call-cue';
import { pictureOf, PICTURES } from './character-body';
import './clinic-panel.css';
import { iconUrl } from './icons';
import { pressedNewsKey } from './keys';
import { amount, counted, listed } from './salvage';
import { NEWS_KEY } from './tuning';

const KEY = NEWS_KEY.toUpperCase();

const PARTS: Record<BodyPart, string> = {
  legs: 'your legs',
  vertebra: 'a vertebra',
  left_eye: 'your left eye',
  right_eye: 'your right eye',
  left_kidney: 'a kidney',
  right_kidney: 'a kidney',
  stomach: 'your stomach',
  feet: 'your feet',
};

const upperFirst = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

/** A part a recipe uses up: how many it takes, and how many they carry. */
export type Need = { name: string; count: number; have: number };

/** One thing the player can do at the clinic: `name` is its row, `label` what Enter does. */
export type Deal =
  | { kind: 'talk'; name: string; label: string; npcId: string }
  | { kind: 'sell'; name: string; label: string; price: number }
  | { kind: 'item'; name: string; label: string; price: number; item: string; count: number }
  | { kind: 'buy'; name: string; label: string; price: number; item: string; count: number; weight: number; short?: 'money' | 'weight' }
  | { kind: 'part'; name: string; label: string; price: number; part: BodyPart }
  | { kind: 'fit'; name: string; label: string; price: number; bionic: Bionic; part: BodyPart; needs: Need[]; short: boolean; blocked?: string }
  | { kind: 'recipe'; name: string; label: string; price: number; bionic: Bionic }
  | { kind: 'treat'; name: string; label: string; price: number; effect: EffectKind | null; short: boolean };

export type Keeper = { id: string; name: string };

export type Side = 'yours' | 'theirs';
export const SIDES: readonly Side[] = ['yours', 'theirs'];

/** Theirs is what they offer: talking, treatments, stock and fittings. Yours is what they'd take from you. */
export const sideOf = ({ kind }: Deal): Side => (kind === 'sell' || kind === 'item' || kind === 'part' || kind === 'recipe' ? 'yours' : 'theirs');

/** Each side's deals, in the order `deals` lists them. */
export function columns(found: readonly Deal[]): Record<Side, Deal[]> {
  return { yours: found.filter((deal) => sideOf(deal) === 'yours'), theirs: found.filter((deal) => sideOf(deal) === 'theirs') };
}

/** The icon id a deal is drawn with from `content/icons/`, whether or not it's painted yet. */
export function iconOf(deal: Deal): string {
  if (deal.kind === 'item' || deal.kind === 'buy') return deal.item;
  if (deal.kind === 'part') return pictureOf({ part: deal.part, state: 'present' });
  if (deal.kind === 'fit') return PICTURES[deal.bionic] ?? deal.bionic;
  if (deal.kind === 'recipe') return 'schematic';
  if (deal.kind === 'treat') return deal.effect ? `treat_${deal.effect}` : 'patch_up';
  return deal.kind === 'sell' ? 'sell_everything' : 'talk';
}

/** Each part `recipe` uses up, named as they carry it, with how many of it they have. */
export function needs(recipe: Recipe | undefined, items: readonly Item[]): Need[] {
  return Object.entries(recipe?.parts ?? {}).map(([id, count]) => {
    const carried = items.filter((item) => item.id === id);
    const name = carried[0]?.name.toLowerCase() ?? id.replaceAll('_', ' ');
    return { name, count, have: carried.length };
  });
}

/** Each kind once, by item id, as it first comes, with how many of it there are. */
export function kinds<T>(things: readonly T[], id: (thing: T) => string): { first: T; count: number }[] {
  const found = new Map<string, { first: T; count: number }>();
  for (const thing of things) {
    const seen = found.get(id(thing));
    if (seen) seen.count += 1;
    else found.set(id(thing), { first: thing, count: 1 });
  }
  return [...found.values()];
}

/** What the player can do at a buyer's panel: talk to the doctor, be treated, sell everything it buys or one of a kind, buy back a part, sell a kidney or a recipe, or be fitted. */
export function deals(buyer: Buyer, player: Player, keeper?: Keeper, recipes: readonly Recipe[] = []): Deal[] {
  const found: Deal[] = [];
  if (keeper) {
    const label = `Talk to ${keeper.name}`;
    found.push({ kind: 'talk', name: label, label, npcId: keeper.id });
  }
  for (const { effect, name, price } of buyer.treatments ?? []) {
    found.push({ kind: 'treat', name, label: name, price, effect, short: player.money < price });
  }
  const sold = player.items.filter(({ id }) => id in buyer.prices);
  const all = sold.filter(({ kind }) => kind !== 'lamp');
  if (all.length > 1) {
    const price = all.reduce((sum, { id }) => sum + buyer.prices[id]!, 0);
    found.push({ kind: 'sell', name: 'Everything', label: `Sell everything: ${listed(counted(all))}`, price });
  }
  for (const { first, count } of kinds(sold, ({ id }) => id)) {
    found.push({ kind: 'item', name: first.name, label: `Sell one: ${first.name}`, price: buyer.prices[first.id]!, item: first.id, count });
  }
  const room = player.carry_limit - player.items.reduce((load, { weight }) => load + weight, 0);
  for (const { first: offer, count } of kinds(buyer.stock ?? [], ({ item }) => item.id)) {
    const { item, price } = offer;
    const label = `Buy back: ${item.name}${count > 1 ? ` ×${count}` : ''}`;
    const short = player.money < price - 1e-9 ? 'money' : item.weight > room + 1e-9 ? 'weight' : undefined;
    found.push({ kind: 'buy', name: item.name, label, price, item: item.id, count, weight: item.weight, ...(short && { short }) });
  }
  for (const [part, price] of Object.entries(buyer.parts ?? {}) as [BodyPart, number][]) {
    found.push({ kind: 'part', name: upperFirst(PARTS[part]), label: `Sell ${PARTS[part]}`, price, part });
  }
  const recipe = (bionic: Bionic) => recipes.find((known) => known.bionic === bionic);
  for (const { bionic, name, price, parts, blocked } of buyer.fittings ?? []) {
    const needed = needs(recipe(bionic), player.items);
    const short = player.money < price || needed.some(({ count, have }) => have < count);
    for (const part of parts) {
      const label = `${name}, in place of ${PARTS[part]}`;
      const row = parts.length > 1 ? `${name}, ${part.replace('_', ' ')}` : name;
      found.push({ kind: 'fit', name: row, label, price, bionic, part, needs: needed, short, ...(blocked && { blocked }) });
    }
  }
  for (const [bionic, price] of Object.entries(buyer.recipes ?? {}) as [Bionic, number][]) {
    const name = recipe(bionic)?.name ?? bionic.replaceAll('_', ' ');
    found.push({ kind: 'recipe', name: `${name} recipe`, label: `Sell your recipe: ${name}`, price, bionic });
  }
  return found;
}

/** What a fitting uses up, against what they have: "copper wire 2/3 · usb c connector 1/1". */
export const needed = (needs: readonly Need[]) => needs.map(({ name, count, have }) => `${name} ${have}/${count}`).join(' · ');

/** What the chosen deal comes to: its price against their credits, what it uses up, or why it's blocked. */
export function details(deal: Deal, money: number): string[] {
  if (deal.kind === 'talk') return [];
  if (deal.kind === 'fit' && deal.blocked) return [deal.blocked];
  if (deal.kind === 'item' && deal.count > 1) return [`Pays ${amount(deal.price)} each`, `You have ${deal.count}`];
  if (sideOf(deal) === 'yours') return [`Pays ${amount(deal.price)}`];
  const lines = [`Costs ${amount(deal.price)} of your ${amount(money)}`];
  if (deal.kind === 'fit' && deal.needs.length) lines.push(needed(deal.needs));
  if (deal.kind === 'buy') lines.push(`Weighs ${amount(deal.weight)} kg${deal.count > 1 ? ` · ${deal.count} for sale` : ''}`);
  return lines;
}

/** What the clinic's panel says of the chosen deal: what Enter will do, or why it can't. */
export function note(deal: Deal | undefined, armed: boolean, money: number): string {
  if (!deal) return '';
  if (deal.kind === 'fit' && deal.blocked) return deal.blocked;
  if (deal.kind === 'fit' && deal.short) {
    const missing = deal.needs.find(({ count, have }) => have < count);
    if (missing) return `It needs ${missing.count} ${missing.name}, and you have ${missing.have}.`;
    return `It costs ${amount(deal.price)}, and you have ${amount(money)}.`;
  }
  if (deal.kind === 'buy') {
    if (deal.short === 'money') return `It costs ${amount(deal.price)}, and you have ${amount(money)}.`;
    if (deal.short === 'weight') return `It weighs ${amount(deal.weight)} kg, more than you can carry now.`;
    return 'Enter to buy it back.';
  }
  if (deal.kind === 'recipe') return "Enter to sell it. You'll still know it, but she buys it only once.";
  if (deal.kind === 'item') return 'Enter to sell one.';
  if (deal.kind === 'treat') return deal.short ? `It costs ${amount(deal.price)}, and you have ${amount(money)}.` : 'Enter to go ahead.';
  if (deal.kind === 'talk' || deal.kind === 'sell') return 'Enter to go ahead.';
  const what = deal.kind === 'part' ? `sell ${PARTS[deal.part]}` : `have this fitted in place of ${PARTS[deal.part]}`;
  return armed ? `Enter again to ${what} for ${amount(deal.price)}. It can't be undone.` : 'Enter to go ahead.';
}

function key(deal: Deal): string {
  if (deal.kind === 'fit') return `fit:${deal.bionic}:${deal.part}`;
  if (deal.kind === 'buy' || deal.kind === 'item') return `${deal.kind}:${deal.item}`;
  if (deal.kind === 'treat') return `treat:${deal.effect}`;
  return deal.kind === 'sell' ? 'sell' : `${deal.kind}:${deal.label}`;
}
const isShort = (deal: Deal) => ((deal.kind === 'fit' || deal.kind === 'treat') && deal.short) || (deal.kind === 'buy' && deal.short !== undefined);
const isBlocked = (deal: Deal) => deal.kind === 'fit' && deal.blocked !== undefined;
const isLamp = (deal: Deal) => deal.kind === 'item' && deal.item === 'lamp';
const count = (deal: Deal) => (deal.kind === 'item' || deal.kind === 'buy' ? deal.count : 1);

function el<K extends keyof HTMLElementTagNameMap>(tag: K, text?: string, className?: string): HTMLElementTagNameMap[K] {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}

/** `index` within `deals`, but off talking and the lamp where there's anything else, so the choice never lands on either by surprise. */
function landing(deals: readonly Deal[], index: number): number {
  const at = Math.min(index, Math.max(deals.length - 1, 0));
  const plain = (i: number) => deals[i] !== undefined && deals[i].kind !== 'talk' && !isLamp(deals[i]);
  if (plain(at)) return at;
  const order = [...deals.keys()].filter((i) => i > at).concat([...deals.keys()].filter((i) => i < at).reverse());
  return order.find(plain) ?? at;
}

/** The deal's icon, or a blank frame where it isn't painted yet. */
function icon(deal: Deal): HTMLElement {
  const cell = el('span', undefined, 'clinic-icon');
  const url = iconUrl(iconOf(deal));
  if (url) {
    const picture = cell.appendChild(el('img'));
    picture.src = url;
    picture.alt = '';
  } else cell.classList.add('clinic-blank');
  if (count(deal) > 1) cell.appendChild(el('span', `×${count(deal)}`, 'clinic-count'));
  return cell;
}

/** A buyer up close, as a trade screen: yours to sell on the left, theirs to buy or be fitted on the right. */
export class ClinicPanel {
  private readonly panel: HTMLElement;
  private readonly title: HTMLElement;
  private readonly money: HTMLElement;
  private readonly lists: Record<Side, HTMLOListElement>;
  private readonly chosen: HTMLElement;
  private readonly status: HTMLElement;
  private readonly send: (message: ClientMessage) => boolean;
  private readonly talk: (npcId: string) => void;
  private shown: Record<Side, Deal[]> = { yours: [], theirs: [] };
  private side: Side = 'yours';
  private at: Record<Side, number> = { yours: 0, theirs: 0 };
  private armed?: string;
  /** The chosen row is gone, so Enter waits for the arrows. */
  private lost = false;
  private drawn = '';
  private cash = 0;

  constructor(parent: HTMLElement, send: (message: ClientMessage) => boolean, talk: (npcId: string) => void) {
    this.send = send;
    this.talk = talk;
    this.panel = parent.appendChild(el('section', undefined, 'clinic'));
    this.panel.tabIndex = -1;
    this.panel.hidden = true;
    this.panel.ariaLabel = 'Clinic';
    callCue.slot(this.panel);
    const header = this.panel.appendChild(el('header'));
    this.title = header.appendChild(el('b'));
    this.money = header.appendChild(el('span', undefined, 'clinic-money'));
    const sides = this.panel.appendChild(el('div', undefined, 'clinic-sides'));
    const list = (side: Side, heading: string, empty: string) => {
      const column = sides.appendChild(el('div', undefined, `clinic-side clinic-${side}`));
      column.appendChild(el('h3', heading));
      const rows = column.appendChild(el('ol'));
      rows.dataset.empty = empty;
      rows.addEventListener('click', (event) => {
        const row = (event.target as Element).closest<HTMLElement>('li[data-index]');
        if (!row) return;
        this.choose(side, Number(row.dataset.index));
        this.act();
      });
      return rows;
    };
    this.lists = { yours: list('yours', 'Yours', 'Nothing they want.'), theirs: list('theirs', 'Theirs', 'Nothing for you.') };
    this.chosen = this.panel.appendChild(el('div', undefined, 'clinic-chosen'));
    const footer = this.panel.appendChild(el('footer'));
    this.status = footer.appendChild(el('p'));
    footer.appendChild(el('span', `← → side · ↑ ↓ choose · Enter · Esc or ${KEY} close`));
    this.panel.addEventListener('keydown', (event) => this.onKey(event));
  }

  get isOpen(): boolean {
    return !this.panel.hidden;
  }

  open(buyer: Buyer, player: Player, keeper?: Keeper, recipes: readonly Recipe[] = []): void {
    const shown = columns(deals(buyer, player, keeper, recipes));
    this.side = shown.yours.length || !shown.theirs.length ? 'yours' : 'theirs';
    this.at = { yours: landing(shown.yours, 0), theirs: landing(shown.theirs, 0) };
    this.shown = shown;
    this.armed = undefined;
    this.lost = false;
    this.drawn = '';
    this.panel.hidden = false;
    this.update(buyer, player, keeper, recipes);
    this.panel.focus();
  }

  close(): void {
    if (this.panel.contains(document.activeElement)) (document.activeElement as HTMLElement).blur();
    this.panel.hidden = true;
  }

  /** Each frame: closes once there's no buyer where they stand, else shows what's on offer now. */
  update(buyer: Buyer | undefined, player: Player | undefined, keeper?: Keeper, recipes: readonly Recipe[] = []): void {
    if (!this.isOpen) return;
    if (!buyer || !player) {
      this.close();
      return;
    }
    const shown = columns(deals(buyer, player, keeper, recipes));
    const drawn = JSON.stringify([buyer.name, player.money, shown, this.side, this.at, this.armed, this.lost]);
    if (drawn === this.drawn) return;
    for (const side of SIDES) {
      const chosen = this.shown[side][this.at[side]];
      const kept = chosen ? shown[side].findIndex((deal) => key(deal) === key(chosen)) : -1;
      if (chosen && kept === -1 && side === this.side) this.lost = true;
      this.at[side] = kept === -1 ? landing(shown[side], this.at[side]) : kept;
    }
    this.shown = shown;
    this.cash = player.money;
    this.title.textContent = buyer.name;
    this.panel.ariaLabel = buyer.name;
    this.money.textContent = `Credits ${amount(player.money)}`;
    this.render();
    this.drawn = JSON.stringify([buyer.name, player.money, shown, this.side, this.at, this.armed, this.lost]);
  }

  private onKey(event: KeyboardEvent): void {
    event.stopPropagation();
    const { key: pressed } = event;
    if (pressed === 'Escape' || pressedNewsKey(event)) {
      event.preventDefault();
      this.close();
    } else if (pressed === 'ArrowLeft' || pressed === 'ArrowRight') {
      event.preventDefault();
      const side = pressed === 'ArrowLeft' ? 'yours' : 'theirs';
      if (this.shown[side].length) this.choose(side, this.at[side]);
    } else if (pressed === 'ArrowDown' || pressed === 'ArrowUp') {
      event.preventDefault();
      const count = this.shown[this.side].length;
      const step = pressed === 'ArrowDown' ? (this.lost ? 0 : 1) : -1;
      if (count) this.choose(this.side, (this.at[this.side] + step + count) % count);
    } else if (pressed === 'Enter' || pressed === ' ') {
      event.preventDefault();
      this.act();
    }
  }

  private get deal(): Deal | undefined {
    return this.shown[this.side][this.at[this.side]];
  }

  private choose(side: Side, index: number): void {
    if (side !== this.side || index !== this.at[side]) this.armed = undefined;
    this.side = side;
    this.at[side] = index;
    this.lost = false;
    this.render();
  }

  private act(): void {
    const deal = this.deal;
    if (!deal || this.lost) return;
    if (deal.kind === 'talk') {
      this.close();
      this.talk(deal.npcId);
    } else if (deal.kind === 'sell') {
      this.send({ type: 'sell', item: null });
    } else if (deal.kind === 'item') {
      this.send({ type: 'sell', item: deal.item });
    } else if (deal.kind === 'recipe') {
      this.send({ type: 'sell_recipe', recipe: deal.bionic });
    } else if (deal.kind === 'buy') {
      if (!deal.short) this.send({ type: 'buy', item: deal.item });
    } else if (deal.kind === 'treat') {
      if (!deal.short) this.send({ type: 'treat', effect: deal.effect });
    } else if (deal.kind === 'fit' && (deal.short || deal.blocked)) {
      this.armed = undefined;
    } else if (this.armed !== key(deal)) {
      this.armed = key(deal);
    } else {
      this.armed = undefined;
      if (deal.kind === 'part') this.send({ type: 'sell_part', part: deal.part });
      else this.send({ type: 'fit', bionic: deal.bionic, part: deal.part });
    }
    this.render();
  }

  private render(): void {
    for (const side of SIDES) {
      const rows = this.shown[side].map((deal, index) => {
        const row = el('li');
        row.dataset.index = String(index);
        const at = index === this.at[side];
        row.classList.toggle('clinic-selected', at && side === this.side && !this.lost);
        row.classList.toggle('clinic-kept', at && side !== this.side);
        row.classList.toggle('clinic-short', isShort(deal));
        row.classList.toggle('clinic-blocked', isBlocked(deal));
        row.classList.toggle('clinic-armed', this.armed === key(deal));
        row.appendChild(icon(deal));
        const name = row.appendChild(el('span', deal.name, 'clinic-name'));
        if (deal.kind === 'fit' && deal.blocked) name.appendChild(el('small', deal.blocked));
        if (deal.kind !== 'talk' && !isBlocked(deal)) row.appendChild(el('b', amount(deal.price)));
        return row;
      });
      this.lists[side].replaceChildren(...rows);
      this.lists[side].parentElement!.classList.toggle('clinic-active', side === this.side);
    }
    const deal = this.lost ? undefined : this.deal;
    this.chosen.replaceChildren(...(deal ? [icon(deal), this.facts(deal)] : []));
    if (this.lost) this.status.textContent = 'Done. Choose the next with the arrows.';
    else this.status.textContent = deal ? note(deal, this.armed === key(deal), this.cash) : 'Nothing to buy or sell here now.';
    this.lists[this.side].querySelector('.clinic-selected')?.scrollIntoView?.({ block: 'nearest' });
  }

  private facts(deal: Deal): HTMLElement {
    const facts = el('div', undefined, 'clinic-facts');
    facts.appendChild(el('b', deal.label));
    for (const line of details(deal, this.cash)) facts.appendChild(el('span', line, isBlocked(deal) ? 'clinic-reason' : undefined));
    return facts;
  }
}
