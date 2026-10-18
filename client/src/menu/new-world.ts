import type { HookKind, NewWorld, Pin } from './api';

export const BONDS: readonly { kind: HookKind; label: string }[] = [
  { kind: 'old_friend', label: 'is an old friend of' },
  { kind: 'rival', label: 'is a rival of' },
  { kind: 'ex_partner', label: 'is the ex of' },
  { kind: 'estranged_sibling', label: 'is the estranged sibling of' },
  { kind: 'debt', label: 'owes money to' },
  { kind: 'secret', label: 'has a secret known to' },
  { kind: 'betrayal', label: 'betrayed' },
  { kind: 'saved_life', label: 'saved the life of' },
];

export const bondLabel = (kind: HookKind) =>
  BONDS.find((bond) => bond.kind === kind)?.label ?? kind;

/** Residents picked by hand, then Randomise's. The server draws for any house still empty. */
export class NewWorldState {
  readonly houses: number;
  count: number;
  private readonly picked: string[] = [];
  private drawn: string[] = [];
  private bonds: Pin[] = [];

  constructor(houses: number, count = houses) {
    this.houses = houses;
    this.count = Math.min(Math.max(count, 1), houses);
  }

  get residents(): string[] {
    return [...this.picked, ...this.drawn];
  }

  get picks(): readonly string[] {
    return this.picked;
  }

  get draws(): readonly string[] {
    return this.drawn;
  }

  get pins(): readonly Pin[] {
    return this.bonds;
  }

  get open(): number {
    return this.count - this.residents.length;
  }

  isPicked(id: string): boolean {
    return this.picked.includes(id);
  }

  isDrawn(id: string): boolean {
    return this.drawn.includes(id);
  }

  /** When every house is taken, the last drawn resident makes way, or else the village grows. */
  toggle(id: string): boolean {
    if (this.isPicked(id) || this.isDrawn(id)) {
      this.remove(id);
      return true;
    }
    if (this.open === 0) {
      const last = this.drawn.at(-1);
      if (last !== undefined) this.remove(last);
      else if (this.count < this.houses) this.count += 1;
      else return false;
    }
    this.picked.push(id);
    return true;
  }

  setCount(count: number): void {
    this.count = Math.min(Math.max(count, this.picked.length, 1), this.houses);
    while (this.residents.length > this.count) this.remove(this.drawn.at(-1)!);
  }

  drawRequest(): NewWorld {
    const pins = this.bonds.filter((pin) => this.isPicked(pin.actor) && this.isPicked(pin.target));
    return { count: this.count, picks: [...this.picked], pins };
  }

  randomised(residents: readonly string[]): void {
    this.drawn = residents
      .filter((id) => !this.isPicked(id))
      .slice(0, this.count - this.picked.length);
    this.bonds = this.bonds.filter((pin) => this.has(pin.actor) && this.has(pin.target));
  }

  pin(pin: Pin): string | null {
    if (pin.actor === pin.target) return 'A bond needs two different residents.';
    if (!this.has(pin.actor) || !this.has(pin.target)) return 'Pick both residents first.';
    const pair = (p: Pin) => [p.actor, p.target].sort().join(' ');
    if (this.bonds.some((p) => pair(p) === pair(pin))) return 'Those two already have a bond.';
    this.bonds.push(pin);
    return null;
  }

  unpin(index: number): void {
    this.bonds.splice(index, 1);
  }

  clear(): void {
    this.picked.length = 0;
    this.drawn = [];
    this.bonds = [];
  }

  request(): NewWorld {
    return { count: this.count, picks: this.residents, pins: [...this.bonds] };
  }

  private has(id: string): boolean {
    return this.isPicked(id) || this.isDrawn(id);
  }

  private remove(id: string): void {
    const list = this.isPicked(id) ? this.picked : this.drawn;
    list.splice(list.indexOf(id), 1);
    this.bonds = this.bonds.filter((pin) => pin.actor !== id && pin.target !== id);
  }
}
