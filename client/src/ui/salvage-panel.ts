import { playerState, server, type Bionic, type Corpse, type Item, type MapTile, type Pile, type Player, type Position, type TakeMessage } from '../net';
import { mapOf } from '../world/map';
import type { Reachable } from '../world/reach';
import { callCue } from './call-cue';
import { kg, many } from './character-panel';
import './clinic-panel.css';
import { pressedNewsKey } from './keys';
import { amount, loadOf, stackFits, totalLoad } from './salvage';
import './salvage-panel.css';
import { el, icon, note, rowsOf, weaponLine, type Row } from './stash-panel';
import { NEWS_KEY } from './tuning';

const KEY = NEWS_KEY.toUpperCase();
/** The server's reach: while they're in it, a take still lands. */
const REACH_TILES = 1.5;
const MONEY_ICON = 'credits';

/** What the screen is open on: a corpse, or the oldest pile they left on a tile. */
export type Source = { corpse: string } | { pile: MapTile };

/** A thing on the body or in the pile that a row takes: an item by where the first like it is, or a bionic by its id. */
export type Thing = { kind: 'money'; id: string; name: string; money: number } | (Row & { kind: 'item'; index: number }) | (Row & { kind: 'bionic' });

/** A row per item, with any just like it counted in, against the `room` they have. */
export function itemRows(items: readonly Item[], room: number): (Row & { kind: 'item'; index: number })[] {
  const rows: (Row & { kind: 'item'; index: number })[] = [];
  items.forEach((item, index) => {
    const same = rows.find(({ first }) => JSON.stringify(first) === JSON.stringify(item));
    if (same) {
      same.count += item.amount ?? 1;
      same.load += loadOf(item);
    } else {
      const { id, name, amount: count = 1 } = item;
      rows.push({ kind: 'item', index, id, name, first: item, count, load: loadOf(item), moves: stackFits(item, room) });
    }
  });
  return rows;
}

const keyOf = (thing: Thing) => `${thing.kind}:${thing.id}:${thing.kind === 'item' ? thing.index : ''}`;

const onTile = (a: MapTile, b: MapTile) => a.map === b.map && a.x === b.x && a.y === b.y;

/** The corpse or pile a source names, while it's there. */
export function holderOf(source: Source, player: Player): Corpse | Pile | undefined {
  if ('corpse' in source) return player.corpses?.find(({ id }) => id === source.corpse);
  return player.left?.find(({ at }) => onTile(at, source.pile));
}

const nameOf = (bionic: Bionic) => {
  const words = bionic.replaceAll('_', ' ');
  return words.charAt(0).toUpperCase() + words.slice(1);
};

const partOf = (bionic: Bionic, parts: readonly Item[]): Item =>
  parts.find(({ id }) => id === bionic) ?? { id: bionic, kind: 'bionic', name: nameOf(bionic), weight: 0, bionic, charge: null, on: null };

/** Its money, then its items, then a row per kind of bionic, each against `room`. */
export function thingsOf(holder: Corpse | Pile, room: number, parts: readonly Item[]): Thing[] {
  const money = holder.money ?? 0;
  const bionics = 'bionics' in holder ? holder.bionics.map((bionic) => partOf(bionic, parts)) : [];
  return [
    ...(money > 0 ? [{ kind: 'money' as const, id: MONEY_ICON, name: 'Money', money }] : []),
    ...itemRows(holder.items, room),
    ...rowsOf(bionics, room).map((row) => ({ ...row, kind: 'bionic' as const })),
  ];
}

/** What Enter sends for a thing, or nothing when none of it fits. */
export function takeOf(source: Source, thing: Thing): TakeMessage | undefined {
  if (thing.kind !== 'money' && thing.moves <= 0) return undefined;
  return {
    type: 'take',
    corpse: 'corpse' in source ? source.corpse : null,
    pile: 'pile' in source ? source.pile : null,
    item: thing.kind === 'item' ? thing.id : null,
    index: thing.kind === 'item' ? thing.index : null,
    bionic: thing.kind === 'bionic' ? (thing.id as Bionic) : null,
  };
}

const noteOf = (thing: Thing | undefined, room: number) => (thing?.kind === 'money' ? 'Enter to take it.' : note(thing, 'take', room));

/** E at a body or a pile they left: what they carry beside what's on it, and Enter takes the chosen thing. */
export class SalvagePanel {
  private readonly panel: HTMLElement;
  private readonly title: HTMLElement;
  private readonly carried: { title: HTMLElement; list: HTMLOListElement };
  private readonly lying: { title: HTMLElement; list: HTMLOListElement };
  private readonly status: HTMLElement;
  private readonly send: (message: TakeMessage) => void;
  private source?: Source;
  private things: Thing[] = [];
  private room = 0;
  private at = 0;
  private drawn = '';

  constructor(parent: HTMLElement, send: (message: TakeMessage) => void = (message) => server.send(message)) {
    this.send = send;
    this.panel = parent.appendChild(el('div', undefined, 'clinic salvage-panel'));
    this.panel.tabIndex = -1;
    this.panel.hidden = true;
    callCue.slot(this.panel);
    this.title = this.panel.appendChild(el('header')).appendChild(el('b'));
    const sides = this.panel.appendChild(el('div', undefined, 'clinic-sides'));
    this.carried = this.column(sides, 'You carry nothing.', false);
    this.lying = this.column(sides, 'Nothing is left.', true);
    this.lying.list.addEventListener('click', (event) => {
      const row = (event.target as Element).closest<HTMLElement>('li[data-index]');
      if (!row) return;
      this.at = Number(row.dataset.index);
      this.render();
      this.act();
    });
    const footer = this.panel.appendChild(el('footer'));
    this.status = footer.appendChild(el('p'));
    footer.appendChild(el('span', `↑ ↓ choose · Enter · Esc or ${KEY} close`));
    this.panel.addEventListener('keydown', (event) => this.onKey(event));
  }

  private column(parent: HTMLElement, empty: string, active: boolean) {
    const box = parent.appendChild(el('div', undefined, active ? 'clinic-side clinic-active' : 'clinic-side'));
    const title = box.appendChild(el('h3'));
    const list = box.appendChild(el('ol'));
    list.dataset.empty = empty;
    return { title, list };
  }

  get isOpen(): boolean {
    return !this.panel.hidden;
  }

  /** E at a pile or a corpse: whether it's one this screen opens on, a corpse or a pile they left. */
  open(used: Extract<Reachable, { kind: 'pile' }>): boolean {
    const state = playerState.latest;
    if (!state) return false;
    if (!used.salvage && !state.player.left?.includes(used.pile)) return false;
    this.source = used.salvage ? { corpse: used.salvage.corpse.id } : { pile: used.pile.at };
    this.panel.hidden = false;
    this.title.textContent = used.salvage ? 'Your body' : 'Left here';
    this.at = 0;
    this.drawn = '';
    this.show(state.player, state.bionics ?? []);
    this.panel.focus();
    return true;
  }

  close(): void {
    if (this.panel.contains(document.activeElement)) (document.activeElement as HTMLElement).blur();
    this.panel.hidden = true;
  }

  /** Each frame: shows what's changed, and closes once it's empty and gone or they've left it. */
  update(position: Position | undefined): void {
    if (!this.isOpen) return;
    const state = playerState.latest;
    const holder = state && this.source && holderOf(this.source, state.player);
    if (!holder || !position || mapOf(position) !== holder.at.map || Math.hypot(holder.at.x - position.x, holder.at.y - position.y) > REACH_TILES) this.close();
    else this.show(state.player, state.bionics ?? []);
  }

  /** Redraws only for a change, keeping the choice on the row it was on. */
  private show(player: Player, parts: readonly Item[]): void {
    const holder = holderOf(this.source!, player);
    if (!holder) return;
    const load = totalLoad(player.items);
    const room = player.carry_limit - load;
    const things = thingsOf(holder, room, parts);
    const mine = itemRows(player.items, Infinity);
    const content = JSON.stringify([things, mine, player.money, player.carry_limit, room]);
    if (content === this.drawn) return;
    const chosen = this.things[this.at];
    const kept = chosen ? things.findIndex((thing) => keyOf(thing) === keyOf(chosen)) : -1;
    this.at = kept !== -1 ? kept : Math.max(Math.min(this.at, things.length - 1), 0);
    this.things = things;
    this.room = room;
    this.drawn = content;
    this.carried.title.textContent = `You carry ${many(load)} of ${kg(player.carry_limit)}`;
    this.lying.title.textContent = 'corpse' in this.source! ? 'On your body' : 'Lying here';
    this.carried.list.replaceChildren(...this.lines(player.money, mine));
    this.render();
  }

  private lines(money: number, rows: readonly Row[]): HTMLElement[] {
    const lines = rows.map((row) => this.rowLine(row));
    if (money > 0) lines.unshift(this.moneyLine(money));
    for (const line of lines) line.classList.add('salvage-held');
    return lines;
  }

  private moneyLine(money: number): HTMLElement {
    const line = el('li');
    line.appendChild(icon(MONEY_ICON));
    line.appendChild(el('span', 'Money', 'clinic-name'));
    line.appendChild(el('b', amount(money)));
    return line;
  }

  private rowLine(row: Row, heavy = false): HTMLElement {
    const line = el('li');
    line.appendChild(icon(row.id));
    const name = line.appendChild(el('span', row.count !== 1 ? `${row.name} ×${many(row.count)}` : row.name, 'clinic-name'));
    if (row.first.kind === 'weapon') name.appendChild(el('small', weaponLine(row.first)));
    if (heavy) name.appendChild(el('small', 'Too heavy'));
    line.appendChild(el('b', kg(row.load)));
    return line;
  }

  private onKey(event: KeyboardEvent): void {
    event.stopPropagation();
    const { key } = event;
    if (key === 'Escape' || pressedNewsKey(event)) {
      event.preventDefault();
      this.close();
    } else if (key === 'ArrowDown' || key === 'ArrowUp') {
      event.preventDefault();
      const count = this.things.length;
      if (count) this.at = (this.at + (key === 'ArrowDown' ? 1 : -1) + count) % count;
      this.render();
    } else if (key === 'Enter' || key === ' ') {
      event.preventDefault();
      if (!event.repeat) this.act();
    } else if (key === 'Tab' || key === 'ArrowLeft' || key === 'ArrowRight') {
      event.preventDefault();
    }
  }

  private act(): void {
    const thing = this.things[this.at];
    const message = thing && this.source && takeOf(this.source, thing);
    if (message) this.send(message);
  }

  private render(): void {
    this.lying.list.replaceChildren(
      ...this.things.map((thing, index) => {
        const short = thing.kind !== 'money' && thing.moves <= 0;
        const line = thing.kind === 'money' ? this.moneyLine(thing.money) : this.rowLine(thing, short);
        line.dataset.index = String(index);
        line.classList.toggle('clinic-selected', index === this.at);
        line.classList.toggle('clinic-short', short);
        return line;
      }),
    );
    this.status.textContent = noteOf(this.things[this.at], this.room);
    this.lying.list.querySelector('.clinic-selected')?.scrollIntoView?.({ block: 'nearest' });
  }
}
