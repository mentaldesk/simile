import { loadMap, mapIds } from './assets';
import type { TiledMap } from './map';

const files = import.meta.glob<string>('../../../content/map/interiors/*.tmj', {
  eager: true,
  query: '?raw',
  import: 'default',
});

const read = async (url: string) => {
  const found = Object.entries(files).find(([path]) => url.endsWith(path.slice(path.lastIndexOf('/'))));
  if (!found) throw new Error(`No map at ${url}`);
  return found[1];
};

/** Every map, read from disk since tests can't fetch. */
export async function loadEveryMap(): Promise<Record<string, TiledMap>> {
  return Object.fromEntries(await Promise.all(mapIds.map(async (id) => [id, await loadMap(id, read)] as const)));
}
