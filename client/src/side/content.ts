import manifestJson from '../../../content/papercraft/manifest.json';
import { Village, type TiledFile } from './maps';
import type { SceneryManifest } from './scenery';

const files = import.meta.glob<string>(
  ['../../../content/street/*.tmj', '../../../content/street/floors/*.tmj'],
  { eager: true, query: '?raw', import: 'default' },
);
const pictures = import.meta.glob<string>('../../../content/papercraft/*/*.webp', {
  eager: true,
  query: '?url',
  import: 'default',
});

const stem = (path: string) => path.slice(path.lastIndexOf('/') + 1, path.lastIndexOf('.'));

/** content/street/'s maps, as Tiled files by map id. */
export const tiledFiles: Record<string, TiledFile> = Object.fromEntries(
  Object.entries(files).map(([path, raw]) => [stem(path), JSON.parse(raw) as TiledFile]),
);

export const village = Village.read(tiledFiles);

export const scenery = manifestJson as unknown as SceneryManifest;

/** A piece's picture, by its manifest key. */
export function pieceUrl(key: string): string {
  const piece = scenery.pieces[key];
  const url = piece && pictures[`../../../content/papercraft/${piece.file}`];
  if (!url) throw new Error(`No papercraft piece ${key}`);
  return url;
}
