import { playerState, server, type Item, type Machine, type MakeMessage, type Material, type Player, type Position, type Product, type RepairMessage } from '../net';
import { interactableAt, type Interactable } from '../world/interactables';
import { mapOf } from '../world/map';
import './clinic-panel.css';
import { iconUrl } from './icons';
import { pressedNewsKey } from './keys';
import './machine-panel.css';
import { amount } from './salvage';
import { NEWS_KEY } from './tuning';

const KEY = NEWS_KEY.toUpperCase();

/** Every machine by id, from `snapshot` and `machine_changed`. */
export const machines = new Map<string, Machine>();

export function resetMachines(all: readonly Machine[] = []): void {
  machines.clear();
  for (const machine of all) machines.set(machine.id, machine);
}

server.on('snapshot', ({ machines: all }) => resetMachines(all));
server.on('machine_changed', ({ machine }) => machines.set(machine.id, machine));

/** The machine whose stand tile they're on: not the maker space's others, which have no `Machine`. */
export function machineAt(position: Position | undefined): { machine: Machine; interactable: Interactable } | undefined {
  if (!position) return undefined;
  const interactable = interactableAt(mapOf(position), position);
  const machine = interactable && machines.get(interactable.id);
  return machine && interactable && { machine, interactable };
}

export type Action = RepairMessage | MakeMessage;

/** One line of the panel: a part it needs, or what Enter does. */
export type Row =
  | { kind: 'part'; id: string; name: string; count: number; have: number }
  | { kind: 'repair'; id: 'repair'; name: string; short: boolean }
  | { kind: 'make'; id: string; name: string; product: Product; have: number; short: boolean; heavy?: string };

const upperFirst = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

/** What they carry of a material. */
export function carried(material: Material, items: readonly Item[]): number {
  return items.filter(({ id }) => id === material).reduce((sum, { amount = 1 }) => sum + amount, 0);
}

/** What they'd carry once `product` is made: what it uses goes, by a material's weight or scrap's kilos. */
export function loadAfter({ item, uses, cost }: Product, items: readonly Item[]): number {
  const used = uses === 'scrap' ? cost : cost * (items.find(({ id }) => id === uses)?.weight ?? 0);
  return items.reduce((sum, { weight, amount = 1 }) => sum + weight * amount, 0) - used + item.weight * (item.amount ?? 1);
}

/** A broken machine's parts against what they carry, then repairing it; a working one's offers. */
export function rowsOf(machine: Machine, items: readonly Item[], limit = Infinity): Row[] {
  if (machine.state === 'working') {
    return machine.makes.map((product) => {
      const have = product.uses === 'scrap' ? product.cost : carried(product.uses, items);
      const stack = product.item.amount ?? 1;
      const made = stack === 1 ? product.item.name : `${product.item.name} ×${amount(stack)}`;
      const after = loadAfter(product, items);
      const heavy = after > limit + 1e-9 ? `You'd end up carrying ${amount(after)} kg, and you can carry ${amount(limit)}.` : undefined;
      return { kind: 'make', id: product.item.id, name: made, product, have, short: have < product.cost - 1e-9, ...(heavy && { heavy }) };
    });
  }
  const parts = Object.entries(machine.parts).map(([id, count]): Row => {
    const held = items.filter((item) => item.id === id);
    return { kind: 'part', id, name: held[0]?.name ?? upperFirst(id.replaceAll('_', ' ')), count, have: held.length };
  });
  const short = parts.some((part) => part.kind === 'part' && part.have < part.count);
  return [...parts, { kind: 'repair', id: 'repair', name: 'Repair it', short }];
}

/** What a row shows at its end: how many of a part, or what it takes against what they have. */
export function counted(row: Row): string {
  if (row.kind === 'part') return `${row.have}/${row.count}`;
  if (row.kind === 'make') return row.product.uses === 'scrap' ? `${amount(row.product.cost)} kg` : `${amount(row.have)}/${amount(row.product.cost)}`;
  return '';
}

/** What the panel says of the chosen row: what Enter will do, or why it can't. */
export function note(chosen: Row | undefined, rows: readonly Row[], kind?: Machine['kind']): string {
  if (!chosen) return kind === 'recycler' ? "You're carrying no scrap it can use. It leaves the parts you'll need." : 'It has nothing to offer yet.';
  if (chosen.kind === 'make') {
    const { uses, cost } = chosen.product;
    if (chosen.short) return `It takes ${amount(cost)} ${uses}, and you have ${amount(chosen.have)}.`;
    return chosen.heavy ?? 'Enter to make it.';
  }
  if (chosen.kind === 'repair' && !chosen.short) return 'Enter to repair it. It uses up these parts.';
  const missing = rows.find((row) => row.kind === 'part' && row.have < row.count);
  return missing?.kind === 'part' ? `It needs ${missing.count} ${missing.name.toLowerCase()}, and you have ${missing.have}.` : '';
}

const actionOf = (machine: Machine, row: Row | undefined): Action | undefined => {
  if (row?.kind === 'repair' && !row.short) return { type: 'repair', machine: machine.id };
  if (row?.kind === 'make' && !row.short && !row.heavy) return { type: 'make', machine: machine.id, item: row.id };
  return undefined;
};

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

const chooses = ({ kind }: Row) => kind !== 'part';

/** A machine up close: the clinic's list, of the parts it needs or what it offers. */
export class MachinePanel {
  private readonly panel: HTMLElement;
  private readonly title: HTMLElement;
  private readonly state: HTMLElement;
  private readonly list: HTMLOListElement;
  private readonly status: HTMLElement;
  private readonly send: (action: Action) => void;
  private shown?: Machine;
  private rows: Row[] = [];
  private at = 0;
  private drawn = '';

  constructor(parent: HTMLElement, send: (action: Action) => void = (action) => server.send(action)) {
    this.send = send;
    this.panel = parent.appendChild(el('div', undefined, 'clinic machine-panel'));
    this.panel.tabIndex = -1;
    this.panel.hidden = true;
    const header = this.panel.appendChild(el('header'));
    this.title = header.appendChild(el('b'));
    this.state = header.appendChild(el('span', undefined, 'clinic-money'));
    const column = this.panel.appendChild(el('div', undefined, 'clinic-side clinic-active'));
    this.list = column.appendChild(el('ol'));
    this.list.dataset.empty = 'Nothing to make yet.';
    this.list.addEventListener('click', (event) => {
      const row = (event.target as Element).closest<HTMLElement>('li[data-index]');
      if (!row) return;
      const index = Number(row.dataset.index);
      if (!chooses(this.rows[index]!)) return;
      this.at = index;
      this.act();
    });
    const footer = this.panel.appendChild(el('footer'));
    this.status = footer.appendChild(el('p'));
    footer.appendChild(el('span', `↑ ↓ choose · Enter · Esc or ${KEY} close`));
    this.panel.addEventListener('keydown', (event) => this.onKey(event));
  }

  get isOpen(): boolean {
    return !this.panel.hidden;
  }

  /** E at a machine: whether there's one here to open. `blocked` is E doing something else here. */
  use(position: Position | undefined, blocked: boolean): boolean {
    const here = machineAt(position);
    if (blocked || !here || !playerState.latest) return false;
    this.open(here.machine, here.interactable.label, playerState.latest.player);
    return true;
  }

  private open(machine: Machine, label: string, player: Player): void {
    this.panel.hidden = false;
    this.title.textContent = label;
    this.panel.ariaLabel = label;
    this.at = 0;
    this.drawn = '';
    this.show(machine, player);
    this.panel.focus();
  }

  close(): void {
    if (this.panel.contains(document.activeElement)) (document.activeElement as HTMLElement).blur();
    this.panel.hidden = true;
  }

  /** What E's prompt is for here, while E would open it. */
  prompt(position: Position | undefined, blocked: boolean): Interactable | undefined {
    return blocked || this.isOpen ? undefined : machineAt(position)?.interactable;
  }

  /** Each frame: shows what's changed, and closes once they've left the machine. */
  update(position: Position | undefined): void {
    if (!this.isOpen) return;
    const here = machineAt(position);
    if (here && here.machine.id === this.shown?.id && playerState.latest) this.show(here.machine, playerState.latest.player);
    else this.close();
  }

  /** Redraws only for a change, keeping the choice on the row it was on. */
  private show(machine: Machine, player: Player): void {
    const rows = rowsOf(machine, player.items, player.carry_limit);
    const drawn = JSON.stringify([machine, rows, this.at]);
    if (drawn === this.drawn) return;
    const chosen = this.rows[this.at]?.id;
    const kept = machine.id === this.shown?.id ? rows.findIndex(({ id }) => id === chosen) : -1;
    const selectable = rows.findIndex(chooses);
    this.at = kept !== -1 && chooses(rows[kept]!) ? kept : Math.max(selectable, 0);
    this.shown = machine;
    this.rows = rows;
    this.state.textContent = machine.state === 'working' ? 'Working' : 'Broken';
    this.render();
    this.drawn = JSON.stringify([machine, rows, this.at]);
  }

  private onKey(event: KeyboardEvent): void {
    event.stopPropagation();
    const { key } = event;
    if (key === 'Escape' || pressedNewsKey(event)) {
      event.preventDefault();
      this.close();
    } else if (key === 'ArrowDown' || key === 'ArrowUp') {
      event.preventDefault();
      this.step(key === 'ArrowDown' ? 1 : -1);
    } else if (key === 'Enter' || key === ' ') {
      event.preventDefault();
      this.act();
    }
  }

  private step(by: number): void {
    const choices = [...this.rows.keys()].filter((index) => chooses(this.rows[index]!));
    if (!choices.length) return;
    const at = choices.indexOf(this.at);
    this.at = choices[(at + by + choices.length) % choices.length]!;
    this.drawn = '';
    this.render();
  }

  private act(): void {
    const action = this.shown && actionOf(this.shown, this.rows[this.at]);
    if (action) this.send(action);
  }

  private render(): void {
    this.list.replaceChildren(
      ...this.rows.map((row, index) => {
        const line = el('li');
        line.dataset.index = String(index);
        line.classList.toggle('clinic-selected', index === this.at && chooses(row));
        const short = row.kind === 'part' ? row.have < row.count : row.short || (row.kind === 'make' && !!row.heavy);
        line.classList.toggle('clinic-short', short);
        line.classList.toggle('machine-part', row.kind === 'part');
        if (row.kind !== 'repair') line.appendChild(icon(row.id));
        line.appendChild(el('span', row.name, 'clinic-name'));
        const count = counted(row);
        if (count) line.appendChild(el('b', count));
        return line;
      }),
    );
    this.status.textContent = note(this.rows[this.at], this.rows, this.shown?.kind);
    this.list.querySelector('.clinic-selected')?.scrollIntoView?.({ block: 'nearest' });
  }
}
