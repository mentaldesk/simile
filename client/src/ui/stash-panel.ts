import { playerState, server, type Item, type Player, type Position, type StashMessage } from '../net';
import { interactableAt, type Interactable } from '../world/interactables';
import { mapOf } from '../world/map';
import { callCue } from './call-cue';
import { kg, stashOf } from './character-panel';
import './clinic-panel.css';
import { iconUrl } from './icons';
import { pressedNewsKey } from './keys';
import { percent } from './lamp-gauge';
import { amount, loadOf, totalLoad } from './salvage';
import { NEWS_KEY } from './tuning';

const KEY = NEWS_KEY.toUpperCase();
const SLACK = 1e-9;
const FINEST = 1_000_000;

export type Action = StashMessage['action'];

/** The lockers whose stand tile they're on. */
export function lockersAt(position: Position | undefined): Interactable | undefined {
  if (!position) return undefined;
  const interactable = interactableAt(mapOf(position), position);
  return interactable?.id === 'lockers' ? interactable : undefined;
}

/** How much of the stack fits in `room` kg, as the server's `fitting` has it. */
export function fitting(item: Item, room: number): number {
  const { kind, weight, amount: many = 1 } = item;
  if (!weight || loadOf(item) <= room + SLACK) return many;
  const fits = (room + SLACK) / weight;
  if (kind === 'rounds') return Math.max(Math.floor(fits), 0);
  if (kind !== 'material') return 0;
  const part = Math.max(Math.floor(fits * FINEST) / FINEST, 0);
  return part > 0 && many - part < 1 / FINEST ? many : part;
}

/** A kind of thing on one side: `first` is what moves, of `count` in all. */
export type Row = { id: string; name: string; first: Item; count: number; load: number; moves: number };

/** A row per id, in the order they got them, against the `room` the other side has for each. */
export function rowsOf(items: readonly Item[], room: number): Row[] {
  const rows = new Map<string, Row>();
  for (const item of items) {
    const row = rows.get(item.id);
    if (row) {
      row.count += item.amount ?? 1;
      row.load += loadOf(item);
    } else {
      const { id, name, amount: many = 1 } = item;
      rows.set(id, { id, name, first: item, count: many, load: loadOf(item), moves: fitting(item, room) });
    }
  }
  return [...rows.values()];
}

/** What the panel says of the chosen row: what Enter will do, or why it can't. */
export function note(row: Row | undefined, action: Action, room: number): string {
  const verb = action === 'store' ? 'store' : 'take';
  if (!row) return action === 'store' ? "You're carrying nothing to store." : 'There is nothing in the lockers to take.';
  const { first, moves } = row;
  if (moves <= 0) {
    const left = kg(Math.max(room, 0));
    return action === 'store' ? `It won't fit. The lockers have ${left} left.` : `It's too heavy. You can carry ${left} more.`;
  }
  const many = first.amount ?? 1;
  return moves < many ? `Enter to ${verb} ${amount(moves)} of ${amount(many)}. The rest won't fit.` : `Enter to ${verb} it.`;
}

function el<K extends keyof HTMLElementTagNameMap>(tag: K, text?: string, className?: string): HTMLElementTagNameMap[K] {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}

function icon(id: string): HTMLElement {
  const cell = el('span', undefined, 'clinic-icon');
  const url = iconUrl(id);
  if (url) {
    const picture = cell.appendChild(el('img'));
    picture.src = url;
    picture.alt = '';
  } else cell.classList.add('clinic-blank');
  return cell;
}

/** The rounds and condition a weapon keeps wherever it is. */
const weaponLine = ({ rounds, capacity, condition }: Item) => (condition ? `${rounds} of ${capacity} rounds, ${percent(condition)}` : 'Worn out');

type Column = { box: HTMLElement; title: HTMLElement; list: HTMLOListElement };

/** Aris's lockers up close: what they carry beside what's in them, and Enter moves the chosen one across. */
export class StashPanel {
  private readonly panel: HTMLElement;
  private readonly columns: Record<Action, Column>;
  private readonly status: HTMLElement;
  private readonly send: (message: StashMessage) => void;
  private rows: Record<Action, Row[]> = { store: [], take: [] };
  private room: Record<Action, number> = { store: 0, take: 0 };
  private side: Action = 'store';
  private at = 0;
  private drawn = '';

  constructor(parent: HTMLElement, send: (message: StashMessage) => void = (message) => server.send(message)) {
    this.send = send;
    this.panel = parent.appendChild(el('div', undefined, 'clinic stash-panel'));
    this.panel.tabIndex = -1;
    this.panel.hidden = true;
    callCue.slot(this.panel);
    this.panel.appendChild(el('header')).appendChild(el('b', 'Lockers'));
    const sides = this.panel.appendChild(el('div', undefined, 'clinic-sides'));
    this.columns = { store: this.column(sides, 'store', 'You carry nothing.'), take: this.column(sides, 'take', 'The lockers are empty.') };
    const footer = this.panel.appendChild(el('footer'));
    this.status = footer.appendChild(el('p'));
    footer.appendChild(el('span', `←→ ↑↓ choose · Enter · Esc or ${KEY} close`));
    this.panel.addEventListener('keydown', (event) => this.onKey(event));
  }

  private column(parent: HTMLElement, side: Action, empty: string): Column {
    const box = parent.appendChild(el('div', undefined, 'clinic-side'));
    const title = box.appendChild(el('h3'));
    const list = box.appendChild(el('ol'));
    list.dataset.empty = empty;
    list.addEventListener('click', (event) => {
      const row = (event.target as Element).closest<HTMLElement>('li[data-index]');
      if (!row) return;
      this.side = side;
      this.at = Number(row.dataset.index);
      this.render();
      this.act();
    });
    return { box, title, list };
  }

  get isOpen(): boolean {
    return !this.panel.hidden;
  }

  /** E at the lockers: whether they're here to open. `blocked` is E doing something else here. */
  use(position: Position | undefined, blocked: boolean): boolean {
    if (blocked || !lockersAt(position) || !playerState.latest) return false;
    this.panel.hidden = false;
    this.side = 'store';
    this.rows = { store: [], take: [] };
    this.at = 0;
    this.drawn = '';
    this.show(playerState.latest.player);
    this.panel.focus();
    return true;
  }

  close(): void {
    if (this.panel.contains(document.activeElement)) (document.activeElement as HTMLElement).blur();
    this.panel.hidden = true;
  }

  /** What E's prompt is for here, while E would open it. */
  prompt(position: Position | undefined, blocked: boolean): Interactable | undefined {
    return blocked || this.isOpen ? undefined : lockersAt(position);
  }

  /** Each frame: shows what's changed, and closes once they've left the lockers. */
  update(position: Position | undefined): void {
    if (!this.isOpen) return;
    if (lockersAt(position) && playerState.latest) this.show(playerState.latest.player);
    else this.close();
  }

  /** Redraws only for a change, keeping the choice on the row it was on. */
  private show(player: Player): void {
    const stash = stashOf(player);
    const [carried, stored] = [totalLoad(player.items), totalLoad(stash.items)];
    const room = { store: stash.limit - stored, take: player.carry_limit - carried };
    const rows = { store: rowsOf(player.items, room.store), take: rowsOf(stash.items, room.take) };
    const titles = { store: `You carry ${amount(carried)} of ${kg(player.carry_limit)}`, take: `In the lockers ${amount(stored)} of ${kg(stash.limit)}` };
    const content = JSON.stringify([rows, titles]);
    if (content !== this.drawn) {
      const chosen = this.rows[this.side][this.at]?.id;
      const kept = rows[this.side].findIndex(({ id }) => id === chosen);
      this.at = kept !== -1 ? kept : Math.max(Math.min(this.at, rows[this.side].length - 1), 0);
      this.rows = rows;
      this.room = room;
      this.columns.store.title.textContent = titles.store;
      this.columns.take.title.textContent = titles.take;
      this.drawn = content;
      this.render();
    }
  }

  private onKey(event: KeyboardEvent): void {
    event.stopPropagation();
    const { key } = event;
    if (key === 'Escape' || pressedNewsKey(event)) {
      event.preventDefault();
      this.close();
    } else if (key === 'ArrowLeft' || key === 'ArrowRight') {
      event.preventDefault();
      this.side = key === 'ArrowLeft' ? 'store' : 'take';
      this.at = Math.max(Math.min(this.at, this.rows[this.side].length - 1), 0);
      this.render();
    } else if (key === 'ArrowDown' || key === 'ArrowUp') {
      event.preventDefault();
      const count = this.rows[this.side].length;
      if (count) this.at = (this.at + (key === 'ArrowDown' ? 1 : -1) + count) % count;
      this.render();
    } else if (key === 'Enter' || key === ' ') {
      event.preventDefault();
      this.act();
    }
  }

  private act(): void {
    const row = this.rows[this.side][this.at];
    if (row && row.moves > 0) this.send({ type: 'stash', item: row.id, action: this.side });
  }

  private render(): void {
    for (const side of ['store', 'take'] as const) {
      const { box, list } = this.columns[side];
      box.classList.toggle('clinic-active', side === this.side);
      list.replaceChildren(
        ...this.rows[side].map((row, index) => {
          const line = el('li');
          line.dataset.index = String(index);
          line.classList.toggle('clinic-selected', side === this.side && index === this.at);
          line.classList.toggle('clinic-short', row.moves <= 0);
          line.appendChild(icon(row.id));
          const name = line.appendChild(el('span', row.count !== 1 ? `${row.name} ×${amount(row.count)}` : row.name, 'clinic-name'));
          if (row.first.kind === 'weapon') name.appendChild(el('small', weaponLine(row.first)));
          line.appendChild(el('b', kg(row.load)));
          return line;
        }),
      );
    }
    this.status.textContent = note(this.rows[this.side][this.at], this.side, this.room[this.side]);
    this.panel.querySelector('.clinic-selected')?.scrollIntoView?.({ block: 'nearest' });
  }
}
