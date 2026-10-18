import villageJson from '../../../content/map/village.tmj?raw';
import { VILLAGE, type TiledMap } from './map';

const interiorUrls = import.meta.glob<string>('../../../content/map/interiors/*.tmj', {
  eager: true,
  query: '?url',
  import: 'default',
});
const atlases = import.meta.glob<object>('../../../content/art/characters/*.json', {
  eager: true,
  import: 'default',
});
const images = import.meta.glob<string>('../../../content/art/characters/*.png', {
  eager: true,
  query: '?url',
  import: 'default',
});

const fileName = (path: string) => path.slice(path.lastIndexOf('/') + 1, path.lastIndexOf('.'));

const interiors = new Map(Object.entries(interiorUrls).map(([path, url]) => [fileName(path), url]));

async function fetchText(url: string): Promise<string> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url}: ${response.status}`);
  return response.text();
}

export const village = JSON.parse(villageJson) as TiledMap;

export const mapIds: readonly string[] = [VILLAGE, ...interiors.keys()];

/** The village, and each interior once it's loaded. */
export const maps: Record<string, TiledMap | undefined> = { [VILLAGE]: village };

/** Fetched rather than bundled, since each interior embeds the tileset. */
export async function loadMap(id: string, read = fetchText): Promise<TiledMap> {
  const loaded = maps[id];
  if (loaded) return loaded;
  const url = interiors.get(id);
  if (!url) throw new Error(`No map ${id}`);
  return (maps[id] = JSON.parse(await read(url)) as TiledMap);
}

export type Character = { key: string; image: string; atlas: object };

export const characters: Character[] = Object.entries(atlases).flatMap(([path, atlas]) => {
  const image = images[path.replace(/\.json$/, '.png')];
  return image ? [{ key: fileName(path), image, atlas }] : [];
});

export const characterKeys = characters.map(({ key }) => key);
