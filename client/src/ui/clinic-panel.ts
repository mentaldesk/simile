import type { Bionic, BodyPart, Buyer, ClientMessage, EffectKind, Item, Player, Recipe } from '../net';
import { callCue } from './call-cue';
import './clinic-panel.css';
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

/** A part a recipe uses up: how many it takes, and how many they carry. */
export type Need = { name: string; count: number; have: number };

/** One thing the player can do at the clinic. */
export type Deal =
  | { kind: 'talk'; label: string; npcId: string }
  | { kind: 'sell'; label: string; price: number }
  | { kind: 'item'; label: string; price: number; item: string; count: number }
  | { kind: 'buy'; label: string; price: number; item: string; weight: number; short?: 'money' | 'weight' }
  | { kind: 'part'; label: string; price: number; part: BodyPart }
  | { kind: 'fit'; label: string; price: number; bionic: Bionic; part: BodyPart; needs: Need[]; short: boolean; blocked?: string }
  | { kind: 'recipe'; label: string; price: number; bionic: Bionic }
  | { kind: 'treat'; label: string; price: number; effect: EffectKind | null; short: boolean };

export type Keeper = { id: string; name: string };

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
  if (keeper) found.push({ kind: 'talk', label: `Talk to ${keeper.name}`, npcId: keeper.id });
  for (const { effect, name, price } of buyer.treatments ?? []) {
    found.push({ kind: 'treat', label: name, price, effect, short: player.money < price });
  }
  const sold = player.items.filter(({ id }) => id in buyer.prices);
  if (sold.length > 1) {
    const price = sold.reduce((sum, { id }) => sum + buyer.prices[id]!, 0);
    found.push({ kind: 'sell', label: `Sell everything: ${listed(counted(sold))}`, price });
  }
  for (const { first, count } of kinds(sold, ({ id }) => id)) {
    found.push({ kind: 'item', label: `Sell one: ${first.name}`, price: buyer.prices[first.id]!, item: first.id, count });
  }
  const room = player.carry_limit - player.items.reduce((load, { weight }) => load + weight, 0);
  for (const { first: offer, count } of kinds(buyer.stock ?? [], ({ item }) => item.id)) {
    const { item, price } = offer;
    const label = `Buy back: ${item.name}${count > 1 ? ` ×${count}` : ''}`;
    const short = player.money < price - 1e-9 ? 'money' : item.weight > room + 1e-9 ? 'weight' : undefined;
    found.push({ kind: 'buy', label, price, item: item.id, weight: item.weight, ...(short && { short }) });
  }
  for (const [part, price] of Object.entries(buyer.parts ?? {}) as [BodyPart, number][]) {
    found.push({ kind: 'part', label: `Sell ${PARTS[part]}`, price, part });
  }
  const recipe = (bionic: Bionic) => recipes.find((known) => known.bionic === bionic);
  for (const { bionic, name, price, parts, blocked } of buyer.fittings ?? []) {
    const needed = needs(recipe(bionic), player.items);
    const short = player.money < price || needed.some(({ count, have }) => have < count);
    for (const part of parts) {
      const label = `${name}, in place of ${PARTS[part]}`;
      found.push({ kind: 'fit', label, price, bionic, part, needs: needed, short, ...(blocked && { blocked }) });
    }
  }
  for (const [bionic, price] of Object.entries(buyer.recipes ?? {}) as [Bionic, number][]) {
    const name = recipe(bionic)?.name ?? bionic.replaceAll('_', ' ');
    found.push({ kind: 'recipe', label: `Sell your recipe: ${name}`, price, bionic });
  }
  return found;
}

/** What a fitting uses up, against what they have: "copper wire 2/3 · usb c connector 1/1". */
export const needed = (needs: readonly Need[]) => needs.map(({ name, count, have }) => `${name} ${have}/${count}`).join(' · ');

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

/** The clinic up close: what the doctor buys and fits, for how much and what parts. */
export class ClinicPanel {
  private readonly panel: HTMLElement;
  private readonly title: HTMLElement;
  private readonly money: HTMLElement;
  private readonly list: HTMLOListElement;
  private readonly status: HTMLElement;
  private readonly send: (message: ClientMessage) => boolean;
  private readonly talk: (npcId: string) => void;
  private shown: Deal[] = [];
  private selected = 0;
  private armed?: string;
  private drawn = '';
  private cash = 0;

  constructor(parent: HTMLElement, send: (message: ClientMessage) => boolean, talk: (npcId: string) => void) {
    this.send = send;
    this.talk = talk;
    this.panel = parent.appendChild(document.createElement('section'));
    this.panel.className = 'clinic';
    this.panel.tabIndex = -1;
    this.panel.hidden = true;
    this.panel.ariaLabel = 'Clinic';
    callCue.slot(this.panel);
    const header = this.panel.appendChild(document.createElement('header'));
    this.title = header.appendChild(document.createElement('b'));
    this.money = this.panel.appendChild(document.createElement('small'));
    this.list = this.panel.appendChild(document.createElement('ol'));
    const footer = this.panel.appendChild(document.createElement('footer'));
    this.status = footer.appendChild(document.createElement('p'));
    footer.appendChild(document.createElement('span')).textContent = `↑ ↓ choose · Enter · Esc or ${KEY} close`;
    this.panel.addEventListener('keydown', (event) => this.onKey(event));
    this.list.addEventListener('click', (event) => {
      const item = (event.target as Element).closest<HTMLElement>('li[data-index]');
      if (!item) return;
      this.choose(Number(item.dataset.index));
      this.act();
    });
  }

  get isOpen(): boolean {
    return !this.panel.hidden;
  }

  open(buyer: Buyer, player: Player, keeper?: Keeper, recipes: readonly Recipe[] = []): void {
    this.selected = 0;
    this.armed = undefined;
    this.panel.hidden = false;
    this.update(buyer, player, keeper, recipes);
    this.panel.focus();
  }

  close(): void {
    if (this.panel.contains(document.activeElement)) (document.activeElement as HTMLElement).blur();
    this.panel.hidden = true;
  }

  /** Each frame: closes once there's no clinic where they stand, else shows what's on offer now. */
  update(buyer: Buyer | undefined, player: Player | undefined, keeper?: Keeper, recipes: readonly Recipe[] = []): void {
    if (!this.isOpen) return;
    if (!buyer || !player) {
      this.close();
      return;
    }
    const shown = deals(buyer, player, keeper, recipes);
    const drawn = JSON.stringify([buyer.name, player.money, shown, this.selected, this.armed]);
    if (drawn === this.drawn) return;
    const chosen = this.shown[this.selected];
    this.shown = shown;
    const kept = chosen ? shown.findIndex((deal) => key(deal) === key(chosen)) : -1;
    this.selected = Math.min(kept === -1 ? this.selected : kept, Math.max(shown.length - 1, 0));
    this.cash = player.money;
    this.title.textContent = buyer.name;
    this.panel.ariaLabel = buyer.name;
    this.money.textContent = `You have ${amount(player.money)}.`;
    this.render();
    this.drawn = JSON.stringify([buyer.name, player.money, shown, this.selected, this.armed]);
  }

  private onKey(event: KeyboardEvent): void {
    event.stopPropagation();
    const { key: pressed } = event;
    if (pressed === 'Escape' || pressedNewsKey(event)) {
      event.preventDefault();
      this.close();
    } else if (pressed === 'ArrowDown' || pressed === 'ArrowUp') {
      event.preventDefault();
      const count = this.shown.length;
      if (count) this.choose((this.selected + (pressed === 'ArrowDown' ? 1 : -1) + count) % count);
    } else if (pressed === 'Enter' || pressed === ' ') {
      event.preventDefault();
      this.act();
    }
  }

  private choose(index: number): void {
    if (index !== this.selected) this.armed = undefined;
    this.selected = index;
    this.render();
  }

  private act(): void {
    const deal = this.shown[this.selected];
    if (!deal) return;
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
    const items = this.shown.map((deal, index) => {
      const item = document.createElement('li');
      item.dataset.index = String(index);
      item.classList.toggle('clinic-selected', index === this.selected);
      item.classList.toggle('clinic-short', isShort(deal));
      item.classList.toggle('clinic-blocked', isBlocked(deal));
      item.classList.toggle('clinic-armed', this.armed === key(deal));
      const label = item.appendChild(document.createElement('span'));
      label.textContent = deal.label;
      if (deal.kind === 'fit' && deal.blocked) label.appendChild(document.createElement('small')).textContent = deal.blocked;
      else if (deal.kind === 'fit' && deal.needs.length) label.appendChild(document.createElement('small')).textContent = needed(deal.needs);
      if (deal.kind === 'item') label.appendChild(document.createElement('small')).textContent = `you have ${deal.count}`;
      if (deal.kind !== 'talk' && !isBlocked(deal)) item.appendChild(document.createElement('b')).textContent = amount(deal.price);
      return item;
    });
    this.list.replaceChildren(...items);
    const deal = this.shown[this.selected];
    this.status.textContent = this.shown.length
      ? note(deal, deal !== undefined && this.armed === key(deal), this.cash)
      : 'Nothing to buy or sell here now.';
    this.list.querySelector('.clinic-selected')?.scrollIntoView?.({ block: 'nearest' });
  }
}
