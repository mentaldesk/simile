import type { TiledMap } from '../world/map';
import { setMaps } from './side-view';

const files = import.meta.glob<string>(
  ['../../../content/street/*.tmj', '../../../content/street/floors/*.tmj'],
  { eager: true, query: '?raw', import: 'default' },
);

const fileName = (path: string) => path.slice(path.lastIndexOf('/') + 1, path.lastIndexOf('.'));

/** content/street/'s maps by id, read from disk. Node tests only: jsdom can't import them. */
export const streets: Record<string, TiledMap> = Object.fromEntries(
  Object.entries(files).map(([path, json]) => [fileName(path), JSON.parse(json) as TiledMap]),
);

/** Tells side views by the street maps, as once part 8 loads them. Returns the undo. */
export const loadStreets = (): (() => void) => setMaps(streets);
