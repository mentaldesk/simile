import { server } from '../net';
import type { EffectKind, Item, Meal, Pile, Player, PlayerStateMessage, Shut, Vital } from '../net';
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
/** Health a real second from which it's coming back as resting in bed brings it, far faster than anywhere else. */
export const RESTING_RATE = 0.1;
/** A bigger rise at once is the clinic or waking, not rest. */
const MOST_REST = 0.1;
const RESTING_MS = 500;
export const RESTING = 'Resting. Your health comes back.';
const COLLAPSED_MS = 6000;
const DAY_MS = 86_400_000;
const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

let simTime: string | undefined;
server.on('snapshot', ({ time }) => (simTime = time));
server.on('clock', ({ time }) => (simTime = time));

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

/** Whether they're resting in bed, from how fast `player_state`'s health climbs: the server heals them there as fast as a plug charges. */
export class Resting {
  private health = 1;
  private at = -Infinity;
  private until = -Infinity;

  update(health: number, now: number): boolean {
    if (health !== this.health) {
      const rise = health - this.health;
      const fast = rise > 0 && rise <= MOST_REST && rise / ((now - this.at) / 1000) >= RESTING_RATE;
      this.until = fast ? now + RESTING_MS : -Infinity;
      this.health = health;
      this.at = now;
    }
    return health < 1 && now < this.until;
  }
}

/** How their health and ailments feel, the infection first: only the clinic ends it. */
export function healthFeeling(player: Player, resting = false): string | undefined {
  const has = (kind: EffectKind) => player.effects?.some((effect) => effect.kind === kind);
  const health = player.health ?? 1;
  if (has('infection')) return "Your bite is infected. It won't heal until the clinic treats it.";
  if (resting && health < 1) return RESTING;
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

const dayOf = (time: string) => Math.floor(Date.parse(time) / DAY_MS);

/** When `opens` is from `now`, in sim time, which is UTC: "today at 17:00", "tomorrow at 7:00", "Tuesday at 11:00". */
export function when(opens: string, now: string | undefined): string {
  const at = new Date(opens);
  const time = `${at.getUTCHours()}:${String(at.getUTCMinutes()).padStart(2, '0')}`;
  const weekday = WEEKDAYS[at.getUTCDay()];
  const days = now === undefined ? undefined : dayOf(opens) - dayOf(now);
  if (days === 0) return `today at ${time}`;
  if (days === 1) return `tomorrow at ${time}`;
  return `${days !== undefined && days >= 7 ? 'next ' : ''}${weekday} at ${time}`;
}

/** Why the shop they stand in isn't serving, and when it next does. */
export function shutPrompt({ name, reason, opens }: Shut, now: string | undefined = simTime): string {
  if (reason === 'sold_out') return `${name} has sold out for this shift.${opens ? ` Opens again ${when(opens, now)}.` : ''}`;
  return `${name} is shut.${opens ? ` Opens ${when(opens, now)}.` : ''}`;
}

/** What F eats, or why the shop they stand in isn't serving, or once they're hungry, where they could eat. */
export function eatPrompt(state: PlayerStateMessage, now: string | undefined = simTime): string | undefined {
  const { player, meal, shut } = state;
  if (onCell(player)) return undefined;
  const eat = toEat(state);
  if (eat?.kind === 'item') return `Press ${key(EAT_KEY)} to eat your ${lowerFirst(eat.item.name)}.`;
  if (shut) return shutPrompt(shut, now);
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
  readonly corner: HTMLElement;
  private readonly lines = new Map<Line, HTMLElement>();
  private readonly resting = new Resting();
  private collapsedUntil = 0;
  private cause: Vital = 'hunger';

  constructor(parent: HTMLElement) {
    const root = (this.corner = parent.appendChild(document.createElement('div')));
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
    const resting = !!state && this.resting.update(state.player.health ?? 1, now);
    this.show('health', state && healthFeeling(state.player, resting));
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
