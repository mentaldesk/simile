import type { Item, Meal, PlayerStateMessage } from '../net';
import { EAT_KEY, NEWS_KEY } from './tuning';

/** Hunger from which F eats. */
export const PECKISH = 0.3;
export const HUNGRY = 0.5;
/** The server collapses the player at 1. */
export const STARVING = 0.85;
const COLLAPSED_MS = 6000;

export type Eat = { kind: 'meal'; meal: Meal } | { kind: 'item'; item: Item };

const amount = (money: number) => String(Number(money.toFixed(2)));
const lowerFirst = (text: string) => text.charAt(0).toLowerCase() + text.slice(1);
const key = (name: string) => name.toUpperCase();

export function feeling(hunger: number): string | undefined {
  if (hunger >= STARVING) return "You're starving. Eat soon, or you'll collapse.";
  if (hunger >= HUNGRY) return "You're hungry.";
  return undefined;
}

/** What F eats once they're peckish: the meal on offer here if they can pay, else the first food they carry. */
export function toEat(state: PlayerStateMessage | undefined): Eat | undefined {
  if (!state || state.player.hunger < PECKISH) return undefined;
  const { player, meal } = state;
  if (meal && meal.price <= player.money) return { kind: 'meal', meal };
  const item = player.items.find(({ kind }) => kind === 'food');
  return item && { kind: 'item', item };
}

/** What F eats, or once they're hungry, where they could eat. */
export function eatPrompt(state: PlayerStateMessage): string | undefined {
  const { player, meal } = state;
  const eat = toEat(state);
  if (eat?.kind === 'item') return `Press ${key(EAT_KEY)} to eat your ${lowerFirst(eat.item.name)}.`;
  if (eat) {
    const { name, price } = eat.meal;
    return `Press ${key(EAT_KEY)} to eat at ${name}${price ? ` for ${amount(price)}` : ''}.`;
  }
  if (player.hunger < HUNGRY) return undefined;
  if (meal) return `A meal at ${meal.name} is ${amount(meal.price)}, and you have ${amount(player.money)}.`;
  return 'Eat at home, or at the café or the noodle bar.';
}

export const COLLAPSED = 'You collapsed from hunger and woke at home.';
export const PICK_UP = `Press ${key(NEWS_KEY)} to pick up what you left here.`;

type Line = 'collapsed' | 'feeling' | 'eat' | 'pile';

/** How hungry the player is and what they can eat, in a corner, and where they can pick up what they left. */
export class HungerHint {
  private readonly lines = new Map<Line, HTMLElement>();
  private collapsedUntil = 0;

  constructor(parent: HTMLElement) {
    const root = parent.appendChild(document.createElement('div'));
    root.className = 'hunger-hint';
    for (const line of ['collapsed', 'feeling', 'eat', 'pile'] as const) {
      const element = root.appendChild(document.createElement('div'));
      element.hidden = true;
      this.lines.set(line, element);
    }
  }

  collapsed(now = Date.now()): void {
    this.collapsedUntil = now + COLLAPSED_MS;
  }

  update(state: PlayerStateMessage | undefined, pile: boolean, now = Date.now()): void {
    this.show('collapsed', now < this.collapsedUntil ? COLLAPSED : undefined);
    this.show('feeling', state && feeling(state.player.hunger));
    this.show('eat', state && eatPrompt(state));
    this.show('pile', pile ? PICK_UP : undefined);
  }

  private show(line: Line, text: string | undefined): void {
    const element = this.lines.get(line)!;
    element.hidden = !text;
    if (text && element.textContent !== text) element.textContent = text;
  }
}
