import manifestJson from '../../../content/papercraft/manifest.json';
import { maps, onLevel } from '../world/assets';
import { readMap, Village } from './maps';
import type { SceneryManifest } from './scenery';

const pictures = import.meta.glob<string>('../../../content/papercraft/*/*.webp', {
  eager: true,
  query: '?url',
  import: 'default',
});

export const village = Village.read(maps);
onLevel((ids) => ids.forEach((id) => village.replace(readMap(id, maps[id]!))));

export const scenery = manifestJson as unknown as SceneryManifest;

export function pieceUrl(key: string): string {
  const piece = scenery.pieces[key];
  const url = piece && pictures[`../../../content/papercraft/${piece.file}`];
  if (!url) throw new Error(`No papercraft piece ${key}`);
  return url;
}
