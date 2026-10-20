import type { Position } from '../net';

export type TiledProperty = { name: string; type: string; value: unknown };
export type TiledObject = {
  name: string;
  type: string;
  properties?: TiledProperty[];
  x?: number;
  y?: number;
  width?: number;
  height?: number;
};
export type TiledLayer = { name: string; type: string; data?: number[]; objects?: TiledObject[] };
export type TiledTileset = { firstgid: number; tiles?: { id: number; properties?: TiledProperty[] }[] };
export type TiledMap = {
  width: number;
  height: number;
  tilewidth: number;
  tileheight: number;
  properties?: TiledProperty[];
  layers: TiledLayer[];
  tilesets?: TiledTileset[];
};

export const COLLISION_LAYER = 'collision';
export const LOCATIONS_LAYER = 'locations';

/** The server always sends a position's map: one without is on none of them. */
export const mapOf = (position: Position): string => position.map ?? '';

export type MapPosition = Position & { map: string };

export type Tile = { x: number; y: number };

/** The tile the server reads a position as: W2's `floor(p + 0.5)`. */
export const tileOf = ({ x, y }: Position): Tile => ({ x: Math.floor(x + 0.5), y: Math.floor(y + 0.5) });

export const objectsOf = (map: TiledMap, layer: string): TiledObject[] =>
  map.layers.find(({ name }) => name === layer)?.objects ?? [];

export const propertyOf = (object: TiledObject, name: string): unknown =>
  object.properties?.find((property) => property.name === name)?.value;

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

export function entryOf(map: TiledMap, locationId: string): Tile | undefined {
  const location = objectsOf(map, LOCATIONS_LAYER).find(({ name }) => name === locationId);
  const [x, y] = location ? [propertyOf(location, 'entry_x'), propertyOf(location, 'entry_y')] : [];
  return typeof x === 'number' && typeof y === 'number' ? { x, y } : undefined;
}
