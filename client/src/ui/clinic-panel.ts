import type { Bionic, BodyPart, Buyer, ClientMessage, Player } from '../net';
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
};

/** One thing the player can do at the clinic. */
export type Deal =
  | { kind: 'talk'; label: string; npcId: string }
  | { kind: 'sell'; label: string; price: number }
  | { kind: 'part'; label: string; price: number; part: BodyPart }
  | { kind: 'fit'; label: string; price: number; bionic: Bionic; part: BodyPart; short: boolean };

export type Keeper = { id: string; name: string };

/** What the player can do at the clinic: talk to the doctor, sell salvage or a kidney, or be fitted. */
export function deals(buyer: Buyer, player: Player, keeper?: Keeper): Deal[] {
  const found: Deal[] = [];
  if (keeper) found.push({ kind: 'talk', label: `Talk to ${keeper.name}`, npcId: keeper.id });
  const sold = player.items.filter(({ id }) => id in buyer.prices);
  if (sold.length) {
    const price = sold.reduce((sum, { id }) => sum + buyer.prices[id]!, 0);
    found.push({ kind: 'sell', label: `Sell your ${listed(counted(sold))}`, price });
  }
  for (const [part, price] of Object.entries(buyer.parts ?? {}) as [BodyPart, number][]) {
    found.push({ kind: 'part', label: `Sell ${PARTS[part]}`, price, part });
  }
  for (const { bionic, name, price, parts } of buyer.fittings ?? []) {
    for (const part of parts) {
      const label = `${name}, in place of ${PARTS[part]}`;
      found.push({ kind: 'fit', label, price, bionic, part, short: player.money < price });
    }
  }
  return found;
}

/** What the clinic's panel says of the chosen deal: what Enter will do, or why it can't. */
export function note(deal: Deal | undefined, armed: boolean, money: number): string {
  if (!deal) return '';
  if (deal.kind === 'fit' && deal.short) return `It costs ${amount(deal.price)}, and you have ${amount(money)}.`;
  if (deal.kind === 'talk' || deal.kind === 'sell') return 'Enter to go ahead.';
  const what = deal.kind === 'part' ? `sell ${PARTS[deal.part]}` : `have this fitted in place of ${PARTS[deal.part]}`;
  return armed ? `Enter again to ${what} for ${amount(deal.price)}. It can't be undone.` : 'Enter to go ahead.';
}

const key = (deal: Deal) => (deal.kind === 'fit' ? `fit:${deal.bionic}:${deal.part}` : `${deal.kind}:${deal.label}`);

/** The clinic up close: what the doctor buys and fits, and for how much. */
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

  open(buyer: Buyer, player: Player, keeper?: Keeper): void {
    this.selected = 0;
    this.armed = undefined;
    this.panel.hidden = false;
    this.update(buyer, player, keeper);
    this.panel.focus();
  }

  close(): void {
    if (this.panel.contains(document.activeElement)) (document.activeElement as HTMLElement).blur();
    this.panel.hidden = true;
  }

  /** Each frame: closes once there's no clinic where they stand, else shows what's on offer now. */
  update(buyer: Buyer | undefined, player: Player | undefined, keeper?: Keeper): void {
    if (!this.isOpen) return;
    if (!buyer || !player) {
      this.close();
      return;
    }
    const shown = deals(buyer, player, keeper);
    const drawn = JSON.stringify([buyer.name, player.money, shown, this.selected, this.armed]);
    if (drawn === this.drawn) return;
    const chosen = this.shown[this.selected];
    this.shown = shown;
    const kept = chosen ? shown.findIndex((deal) => key(deal) === key(chosen)) : -1;
    this.selected = Math.min(kept === -1 ? this.selected : kept, Math.max(shown.length - 1, 0));
    this.cash = player.money;
    this.title.textContent = buyer.name;
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
    } else if (deal.kind === 'fit' && deal.short) {
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
      item.classList.toggle('clinic-short', deal.kind === 'fit' && deal.short);
      item.classList.toggle('clinic-armed', this.armed === key(deal));
      item.appendChild(document.createElement('span')).textContent = deal.label;
      if (deal.kind !== 'talk') item.appendChild(document.createElement('b')).textContent = amount(deal.price);
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
