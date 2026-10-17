import villageJson from '../../../content/map/village.tmj?raw';
import type { TiledMap } from './map';

const atlases = import.meta.glob<object>('../../../content/art/characters/*.json', {
  eager: true,
  import: 'default',
});
const images = import.meta.glob<string>('../../../content/art/characters/*.png', {
  eager: true,
  query: '?url',
  import: 'default',
});

export const village = JSON.parse(villageJson) as TiledMap;

export type Character = { key: string; image: string; atlas: object };

export const characters: Character[] = Object.entries(atlases).flatMap(([path, atlas]) => {
  const image = images[path.replace(/\.json$/, '.png')];
  const key = path.slice(path.lastIndexOf('/') + 1, -'.json'.length);
  return image ? [{ key, image, atlas }] : [];
});

export const characterKeys = characters.map(({ key }) => key);
