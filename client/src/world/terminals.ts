import type { Position } from '../net';
import { LOCATIONS_LAYER, type TiledMap } from './map';
import { TERMINAL_REACH_TILES } from './tuning';

/** A news terminal location, its area in tiles. */
export type Terminal = { id: string; label: string; x: number; y: number; width: number; height: number };

export function terminalsOf(map: TiledMap): Terminal[] {
  const objects = map.layers.find(({ name }) => name === LOCATIONS_LAYER)?.objects ?? [];
  return objects
    .filter(({ type }) => type === 'terminal')
    .map((object) => {
      const label = object.properties?.find(({ name }) => name === 'label')?.value;
      return {
        id: object.name,
        label: typeof label === 'string' ? label : object.name,
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
  const [x, y] = [Math.floor(position.x + 0.5), Math.floor(position.y + 0.5)];
  const reach = TERMINAL_REACH_TILES;
  return terminals.find(
    (t) =>
      x >= t.x - reach && x < t.x + t.width + reach && y >= t.y - reach && y < t.y + t.height + reach,
  );
}
