import type { Position } from '../net';

export type TiledProperty = { name: string; type: string; value: unknown };
export type TiledObject = { name: string; type: string; properties?: TiledProperty[] };
export type TiledLayer = { name: string; type: string; data?: number[]; objects?: TiledObject[] };
export type TiledMap = {
  width: number;
  height: number;
  tilewidth: number;
  tileheight: number;
  layers: TiledLayer[];
};

export const COLLISION_LAYER = 'collision';
export const LOCATIONS_LAYER = 'locations';

export class CollisionMap {
  readonly width: number;
  readonly height: number;
  private readonly cells: readonly number[];

  constructor(width: number, height: number, cells: readonly number[]) {
    this.width = width;
    this.height = height;
    this.cells = cells;
  }

  static of(map: TiledMap): CollisionMap {
    const layer = map.layers.find(({ name }) => name === COLLISION_LAYER);
    return new CollisionMap(map.width, map.height, layer?.data ?? []);
  }

  /** Everything off the map blocks. */
  blocks(x: number, y: number): boolean {
    if (x < 0 || y < 0 || x >= this.width || y >= this.height) return true;
    return (this.cells[y * this.width + x] ?? 0) !== 0;
  }
}

export function entryOf(map: TiledMap, locationId: string): Position | undefined {
  const location = map.layers
    .find(({ name }) => name === LOCATIONS_LAYER)
    ?.objects?.find(({ name }) => name === locationId);
  const property = (name: string) => location?.properties?.find((p) => p.name === name)?.value;
  const [x, y] = [property('entry_x'), property('entry_y')];
  return typeof x === 'number' && typeof y === 'number' ? { x, y } : undefined;
}
