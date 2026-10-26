import type { EffectKind, Item, Meal, Pile, Player, PlayerStateMessage, Vital } from '../net';
import { amount, pickUpPrompt, sellPrompt } from './salvage';
import { EAT_KEY } from './tuning';

/** Hunger from which F eats. */
export const PECKISH = 0.3;
export const HUNGRY = 0.5;
/** The server collapses the player at 1. */
export const STARVING = 0.85;
/** Power from which they're warned to charge, and from which they're told they'll collapse. */
export const LOW_POWER = 0.3;
export const FLAT = 0.1;
/** Health from which they're told they're hurt, and from which they're warned they'll collapse. */
export const HURT = 0.6;
export const BADLY_HURT = 0.25;
const COLLAPSED_MS = 6000;

export type Eat = { kind: 'meal'; meal: Meal } | { kind: 'item'; item: Item };

const lowerFirst = (text: string) => text.charAt(0).toLowerCase() + text.slice(1);
const key = (name: string) => name.toUpperCase();

/** Whether a power cell has taken their stomach's place, so they run on power and never eat. */
export const onCell = (player: Player): boolean => player.body.stomach?.startsWith('power_cell') ?? false;

export function feeling(hunger: number): string | undefined {
  if (hunger >= STARVING) return "You're starving. Eat soon, or you'll collapse.";
  if (hunger >= HUNGRY) return "You're hungry.";
  return undefined;
}

export function powerFeeling(power: number): string | undefined {
  if (power <= FLAT) return "Your power cell is nearly flat. Charge it at a plug, or you'll collapse.";
  if (power <= LOW_POWER) return 'Your power is low. Charge it at a plug.';
  return undefined;
}

/** How their health and ailments feel, the infection first: only the clinic ends it. */
export function healthFeeling(player: Player): string | undefined {
  const has = (kind: EffectKind) => player.effects?.some((effect) => effect.kind === kind);
  const health = player.health ?? 1;
  if (has('infection')) return "Your bite is infected. It won't heal until the clinic treats it.";
  if (health <= BADLY_HURT) return "You're badly hurt. Rest at home or get patched up at the clinic, or you'll collapse.";
  if (has('rat_bite')) return 'A rat bit you. Have the clinic clean it before it turns.';
  if (health <= HURT) return "You're hurt. Rest at home to heal faster.";
  return undefined;
}

const feelingOf = (player: Player): string | undefined =>
  onCell(player) ? powerFeeling(player.power ?? 1) : feeling(player.hunger);

/** What F eats once they're peckish: the meal on offer here if they can pay, else the first food they carry. */
export function toEat(state: PlayerStateMessage | undefined): Eat | undefined {
  if (!state || onCell(state.player) || state.player.hunger < PECKISH) return undefined;
  const { player, meal } = state;
  if (meal && meal.price <= player.money) return { kind: 'meal', meal };
  const item = player.items.find(({ kind }) => kind === 'food');
  return item && { kind: 'item', item };
}

/** What F eats, or once they're hungry, where they could eat. */
export function eatPrompt(state: PlayerStateMessage): string | undefined {
  const { player, meal } = state;
  if (onCell(player)) return undefined;
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

export const COLLAPSED: Record<Vital, string> = {
  hunger: 'You collapsed from hunger and woke at home.',
  power: 'Your power cell ran flat. You collapsed and woke at home.',
  health: 'You collapsed from your wounds and woke at home.',
};

type Line = 'collapsed' | 'feeling' | 'health' | 'eat' | 'pile' | 'sell';

/** How hungry the player is and what they can eat, or how much power they have, and how hurt they are, in a corner, and what they can pick up or sell where they stand. */
export class HungerHint {
  private readonly lines = new Map<Line, HTMLElement>();
  private collapsedUntil = 0;
  private cause: Vital = 'hunger';

  constructor(parent: HTMLElement) {
    const root = parent.appendChild(document.createElement('div'));
    root.className = 'hunger-hint';
    for (const line of ['collapsed', 'feeling', 'health', 'eat', 'pile', 'sell'] as const) {
      const element = root.appendChild(document.createElement('div'));
      element.hidden = true;
      this.lines.set(line, element);
    }
  }

  collapsed(cause: Vital = 'hunger', now = Date.now()): void {
    this.cause = cause;
    this.collapsedUntil = now + COLLAPSED_MS;
  }

  /** `pile` is the one E picks up from, if any. */
  update(state: PlayerStateMessage | undefined, pile: Pile | undefined, now = Date.now()): void {
    this.show('collapsed', now < this.collapsedUntil ? COLLAPSED[this.cause] : undefined);
    this.show('feeling', state && feelingOf(state.player));
    this.show('health', state && healthFeeling(state.player));
    this.show('eat', state && eatPrompt(state));
    this.show('pile', state && pile && pickUpPrompt(pile, state.player));
    this.show('sell', state?.buyer ? sellPrompt(state.buyer, state.player) : undefined);
  }

  private show(line: Line, text: string | undefined): void {
    const element = this.lines.get(line)!;
    element.hidden = !text;
    if (text && element.textContent !== text) element.textContent = text;
  }
}
