import type { Position } from '../net';
import { mapOf, type TiledMap, type TiledProperty } from '../world/map';

type Maps = Readonly<Record<string, (TiledMap & { properties?: TiledProperty[] }) | undefined>>;

let loaded: Maps = {};

/** The maps to tell side views by: `world/assets.ts`'s `maps`, which the dialogue scene sets. */
export function setMaps(maps: Maps): () => void {
  loaded = maps;
  return () => {
    if (loaded === maps) loaded = {};
  };
}

/** Whether a loaded map is drawn from the side, by its `view: side` property (content/street/README.md). */
export function sideView(mapId: string): boolean {
  const properties = loaded[mapId]?.properties ?? [];
  return properties.some(({ name, value }) => name === 'view' && value === 'side');
}

/**
 * Tiles between two positions, for earshot and reach: along x on a side-view map, in a straight
 * line on an iso one. Undefined on different maps, so another floor or street is out of reach.
 */
export function tilesApart(a: Position, b: Position): number | undefined {
  if (mapOf(a) !== mapOf(b)) return undefined;
  return sideView(mapOf(a)) ? Math.abs(b.x - a.x) : Math.hypot(b.x - a.x, b.y - a.y);
}
