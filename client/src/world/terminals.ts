import type { Position } from '../net';
import { LOCATIONS_LAYER, mapOf, objectsOf, propertyOf, tileOf, VILLAGE, type TiledMap } from './map';
import { TERMINAL_REACH_TILES } from './tuning';

/** A news terminal location, its area in tiles. */
export type Terminal = {
  id: string;
  label: string;
  map: string;
  x: number;
  y: number;
  width: number;
  height: number;
};

export function terminalsOf(map: TiledMap, id = VILLAGE): Terminal[] {
  return objectsOf(map, LOCATIONS_LAYER)
    .filter(({ type }) => type === 'terminal')
    .map((object) => {
      const label = propertyOf(object, 'label');
      return {
        id: object.name,
        label: typeof label === 'string' ? label : object.name,
        map: id,
        x: (object.x ?? 0) / map.tilewidth,
        y: (object.y ?? 0) / map.tileheight,
        width: (object.width ?? 0) / map.tilewidth,
        height: (object.height ?? 0) / map.tileheight,
      };
    });
}

/** The terminal within reach of the tile the player stands on, as the server reads it. */
export function terminalAt(
  terminals: readonly Terminal[],
  position: Position | undefined,
): Terminal | undefined {
  if (!position) return undefined;
  const { x, y } = tileOf(position);
  const reach = TERMINAL_REACH_TILES;
  return terminals.find(
    (t) =>
      t.map === mapOf(position) &&
      x >= t.x - reach &&
      x < t.x + t.width + reach &&
      y >= t.y - reach &&
      y < t.y + t.height + reach,
  );
}
