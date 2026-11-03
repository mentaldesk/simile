import iconManifest from '../../../content/icons/icons.json';
import type { Item, Pile } from '../net';

const ICONS: Record<string, unknown> = iconManifest.icons;
const HEAP = 3;

export type Loot = { items?: readonly Item[]; money?: number; teaches?: string };

/** The icons a heap of loot shows, up to three: a schematic for a recipe, coins for cash, then each kind of item. */
export function lootIcons({ items = [], money, teaches }: Loot): string[] {
  const icons = [
    ...(teaches ? ['schematic'] : []),
    ...(money ? ['credits'] : []),
    ...items.map(({ id }) => (ICONS[id] ? id : 'unknown_item')),
  ];
  return [...new Set(icons)].slice(0, HEAP);
}

const itemsOf = ({ at, items, money }: Pile) => `${at.map}:${at.x},${at.y}:${items.map(({ id }) => id).join()}:${money ?? 0}`;

/** Whether two lists of piles lie in the same places and hold the same, as each `player_state` sends them anew. */
export const sameItems = (a: readonly Pile[], b: readonly Pile[]): boolean =>
  a.length === b.length && a.every((pile, i) => pile === b[i] || itemsOf(pile) === itemsOf(b[i]));
