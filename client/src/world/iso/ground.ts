import type { Position } from '../../net';
import type { TiledMap, TiledProperty } from '../map';

type TiledTileset = { firstgid: number; tiles?: { id: number; properties?: TiledProperty[] }[] };
export type TiledMapWithTiles = TiledMap & { tilesets: TiledTileset[] };

const GROUND_LAYER = 'ground';

function tileNames(map: TiledMapWithTiles): Map<number, string> {
  const names = new Map<number, string>();
  for (const { firstgid, tiles = [] } of map.tilesets) {
    for (const { id, properties = [] } of tiles) {
      const name = properties.find((property) => property.name === 'name')?.value;
      if (typeof name === 'string') names.set(firstgid + id, name);
    }
  }
  return names;
}

/** Metres up of the ground an entity stands on, as `ground_height` in `simile/art/iso/town.py`. */
export function groundHeights(
  map: TiledMapWithTiles,
  heights: Record<string, number>,
): (position: Position) => number {
  const names = tileNames(map);
  const data = map.layers.find(({ name }) => name === GROUND_LAYER)?.data ?? [];
  const metres = data.map((gid) => {
    const name = names.get(gid) ?? '';
    return Object.entries(heights).find(([prefix]) => name.startsWith(prefix))?.[1] ?? 0;
  });
  return ({ x, y }) => {
    const [column, row] = [Math.floor(x + 0.5), Math.floor(y + 0.5)];
    const inside = column >= 0 && row >= 0 && column < map.width && row < map.height;
    return inside ? (metres[row * map.width + column] ?? 0) : 0;
  };
}
