import { dolls } from '../dolls/assets';
import type { DollManifest } from '../dolls/manifest';
import type { TiledMap } from './map';

const files = import.meta.glob<string>(
  ['../../../content/street/*.tmj', '../../../content/street/floors/*.tmj'],
  { eager: true, query: '?raw', import: 'default' },
);

const fileName = (path: string) => path.slice(path.lastIndexOf('/') + 1, path.lastIndexOf('.'));

/** Every street and floor, by id. One object, never replaced, since `ui/side-view.ts` reads it. */
export const maps: Record<string, TiledMap | undefined> = {};
for (const [path, json] of Object.entries(files)) maps[fileName(path)] = JSON.parse(json) as TiledMap;

export const mapIds: readonly string[] = Object.keys(maps);

export { dolls };

const PLAYER = 'player';
const residentDolls = Object.keys(dolls)
  .filter((id) => id !== PLAYER)
  .sort();

function fnv1a(text: string): number {
  let hash = 0x811c9dc5;
  for (let i = 0; i < text.length; i++) hash = Math.imul(hash ^ text.charCodeAt(i), 0x01000193);
  return hash >>> 0;
}

/** Its own doll, or a resident's picked by its id, the same one every time. */
export function dollFor(id: string): DollManifest {
  return dolls[id] ?? dolls[residentDolls[fnv1a(id) % residentDolls.length]];
}
