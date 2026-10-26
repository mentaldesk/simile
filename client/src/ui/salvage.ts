import type { Buyer, Item, Pile, Player } from '../net';
import { fits, isClinic } from '../world/buyers';
import { NEWS_KEY } from './tuning';

const E = NEWS_KEY.toUpperCase();

export const amount = (money: number) => String(Number(money.toFixed(2)));
const lowerFirst = (text: string) => text.charAt(0).toLowerCase() + text.slice(1);
const upperFirst = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

/** "a", "a and b", or "a, b and c". */
export function listed(parts: readonly string[]): string {
  return parts.length < 2 ? (parts[0] ?? '') : `${parts.slice(0, -1).join(', ')} and ${parts.at(-1)}`;
}

/** Each kind once, with how many: "copper wire ×2". */
export function counted(items: readonly Item[]): string[] {
  const counts = new Map<string, number>();
  for (const { name } of items) counts.set(lowerFirst(name), (counts.get(lowerFirst(name)) ?? 0) + 1);
  return [...counts].map(([name, n]) => (n > 1 ? `${name} ×${n}` : name));
}

/** What of a pile fits under their carry limit, in order, as the server takes it. */
export function fitting(pile: Pile, player: Player): { taken: Item[]; kept: Item[] } {
  let room = player.carry_limit - player.items.reduce((load, item) => load + item.weight, 0);
  const taken: Item[] = [];
  const kept: Item[] = [];
  for (const item of pile.items) {
    if (item.weight <= room + 1e-9) {
      taken.push(item);
      room -= item.weight;
    } else kept.push(item);
  }
  return { taken, kept };
}

/** What E picks up from a pile in reach: one they left, or salvage or a secret lying about. */
export function pickUpPrompt(pile: Pile, player: Player): string {
  const theirs = player.left?.includes(pile) ?? false;
  const { taken, kept } = fitting(pile, player);
  const money = pile.money ?? 0;
  const names = (items: Item[]) => counted(items).map((name) => `the ${name}`);
  if (!taken.length && !money) {
    if (theirs) return "You can't carry any more of what you left here.";
    const are = kept.length > 1 ? 'are' : 'is';
    return `${upperFirst(listed(names(kept)))} ${are} too heavy to carry with what you have.`;
  }
  if (theirs) return `Press ${E} to pick up ${kept.length ? 'what you can carry of ' : ''}what you left here.`;
  const what = listed([...names(taken), ...(money ? [`${amount(money)} in cash`] : [])]);
  const left = kept.length ? ` ${upperFirst(listed(names(kept)))} won't fit.` : '';
  return `Press ${E} to pick up ${what}.${left}`;
}

/** What E sells to the buyer where they stand, or that it buys. */
export function sellPrompt(buyer: Buyer, player: Player): string {
  if (isClinic(buyer)) return `Press ${E} to see what ${lowerFirst(buyer.name)} buys and ${fits(buyer) ? 'fits' : 'sells'}.`;
  const sold = player.items.filter(({ id }) => id in buyer.prices);
  if (!sold.length) return `${buyer.name} buys salvage. You have ${amount(player.money)}.`;
  const total = sold.reduce((sum, { id }) => sum + buyer.prices[id]!, 0);
  const kinds = counted(sold);
  const what = kinds.length > 2 ? 'your salvage' : `your ${listed(kinds)}`;
  return `Press ${E} to sell ${what} at ${lowerFirst(buyer.name)} for ${amount(total)}.`;
}
