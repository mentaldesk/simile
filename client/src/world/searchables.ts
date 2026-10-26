import type { Item, Pile } from '../net';
import { maps } from './assets';
import { interactablesOn, theLabel, type Interactable } from './interactables';

/** Whether it holds anything or teaches a recipe, which a jack must to be searched. */
export const holds = (thing: Interactable): boolean => !!thing.items?.length || !!thing.teaches;

/** Whether E searches it, as the server does: a searchable, or a jack that holds something once the datajack works it, not yet searched. */
export function searches(thing: Interactable, searched: readonly string[], jacked: boolean): boolean {
  if (searched.includes(thing.id)) return false;
  return thing.kind === 'searchable' || (thing.kind === 'jack' && jacked && holds(thing));
}

/** "copper wire", but "USB-C connector". */
const named = (name: string) => (/^.\p{Ll}/u.test(name) ? name.charAt(0).toLowerCase() + name.slice(1) : name);
const article = (name: string) => (/^[aeiou]/.test(name) ? 'an' : 'a');
const plural = (name: string) => (/[^aeiou]y$/.test(name) ? `${name.slice(0, -1)}ies` : `${name}s`);
const NUMBERS = ['', 'one', 'two', 'three', 'four', 'five', 'six'];

/** "a USB-C connector and two copper wires" */
export function listed(items: readonly Item[]): string {
  const counts = new Map<string, number>();
  for (const { name } of items) counts.set(named(name), (counts.get(named(name)) ?? 0) + 1);
  const each = [...counts].map(([name, n]) => (n === 1 ? `${article(name)} ${name}` : `${NUMBERS[n] ?? n} ${plural(name)}`));
  return each.length > 1 ? `${each.slice(0, -1).join(', ')} and ${each.at(-1)}` : (each[0] ?? '');
}

/** "the datajack", "the power cell, grade 2" */
const bionicName = (bionic: string) => `the ${bionic.replaceAll('_', ' ').replace(/ (\d)$/, ', grade $1')}`;

/** What E at it says: what's in it, and the recipe it teaches. */
export function foundIn(thing: Interactable): string {
  const found = thing.items?.length ? [`find ${listed(thing.items)}`] : [];
  if (thing.teaches) found.push(`learn how to build ${bionicName(thing.teaches)}`);
  return found.length ? `You ${found.join(' and ')}.` : `There's nothing in ${theLabel(thing.label)}.`;
}

const glints = new WeakMap<Interactable, Pile>();

/** A pile to glint at each thing still to search on the maps `on`, the same object each time. */
export function toSearch(searched: readonly string[], jacked: boolean, on: readonly string[] = Object.keys(maps)): Pile[] {
  return on.flatMap((map) =>
    interactablesOn(map)
      .filter((thing) => holds(thing) && searches(thing, searched, jacked))
      .map((thing) => {
        let pile = glints.get(thing);
        if (!pile) {
          const middle = thing.stand[Math.floor(thing.stand.length / 2)]!;
          glints.set(thing, (pile = { at: { map, x: middle.x, y: middle.y }, items: thing.items ?? [] }));
        }
        return pile;
      }),
  );
}
