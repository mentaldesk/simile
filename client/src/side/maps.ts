import type { Position } from '../net';

/** The parts of a Tiled map that content/street/README.md describes. */
export type TiledProperty = { name: string; type: string; value: unknown };
export type TiledObject = {
  name: string;
  type: string;
  x: number;
  y: number;
  width: number;
  height: number;
  properties?: TiledProperty[];
};
export type TiledLayer = { name: string; type: string; data?: number[]; objects?: TiledObject[] };
export type TiledFile = {
  width: number;
  height: number;
  tilewidth: number;
  tileheight: number;
  properties?: TiledProperty[];
  layers: TiledLayer[];
  tilesets: { firstgid: number; tiles?: { id: number; properties?: TiledProperty[] }[] }[];
};

export type Cell = { x: number; y: number };
export type ClimbKind = 'stairs' | 'ladder';
export type LinkKind = 'door' | 'stairs' | 'ladder' | 'lift';

/** An object's cells and properties. */
export type Placed = Cell & {
  name: string;
  type: string;
  w: number;
  h: number;
  props: Record<string, unknown>;
};

/** One end of a door, stairs, ladder or lift, on `map`. */
export type Link = Cell & {
  id: string;
  kind: LinkKind;
  map: string;
  side: 'inside' | 'outside';
  to: Cell & { map: string };
};

export type SideMap = {
  id: string;
  kind: 'street' | 'floor';
  width: number;
  height: number;
  label?: string;
  building?: string;
  floor: number;
  room?: string;
  /** The street it's drawn on, itself for a street. */
  street: string;
  /** The street cell under its top-left cell. */
  offset: Cell;
  solid: Uint8Array;
  /** 0, or 1 + the index of its kind in `CLIMB_KINDS`. */
  climbable: Uint8Array;
  walkable: Uint8Array;
  buildings: Placed[];
  furniture: Placed[];
  locations: Placed[];
  murals: Placed[];
  links: Link[];
  interactables: Placed[];
  spots: Placed[];
  file: TiledFile;
};

export const CLIMB_KINDS: readonly ClimbKind[] = ['stairs', 'ladder'];

const propsOf = (properties: TiledProperty[] = []): Record<string, unknown> =>
  Object.fromEntries(properties.map(({ name, value }) => [name, value]));

function cellsOf(file: TiledFile, object: TiledObject): Cell & { w: number; h: number } {
  return {
    x: Math.round(object.x / file.tilewidth),
    y: Math.round(object.y / file.tileheight),
    w: Math.round(object.width / file.tilewidth),
    h: Math.round(object.height / file.tileheight),
  };
}

function objects(file: TiledFile, layer: string): Placed[] {
  const found = file.layers.find(({ name }) => name === layer)?.objects ?? [];
  return found.map((object) => ({
    name: object.name,
    type: object.type,
    ...cellsOf(file, object),
    props: propsOf(object.properties),
  }));
}

function tiles(file: TiledFile, layer: string, value: (gid: number) => number): Uint8Array {
  const cells = new Uint8Array(file.width * file.height);
  const data = file.layers.find(({ name }) => name === layer)?.data ?? [];
  data.forEach((gid, i) => (cells[i] = gid ? value(gid) : 0));
  return cells;
}

/** A side-view map, read from its Tiled file. */
export function readMap(id: string, file: TiledFile): SideMap {
  const props = propsOf(file.properties);
  const names = new Map<number, unknown>();
  for (const { firstgid, tiles: described = [] } of file.tilesets) {
    for (const tile of described) names.set(firstgid + tile.id, propsOf(tile.properties).name);
  }
  const climbCode = (gid: number) => CLIMB_KINDS.indexOf(names.get(gid) as ClimbKind) + 1;
  const kind = props.kind === 'floor' ? 'floor' : 'street';
  const links = objects(file, 'doors').map(
    ({ name, x, y, props: p }): Link => ({
      id: name,
      kind: (p.kind as LinkKind | undefined) ?? 'door',
      map: id,
      x,
      y,
      side: p.side === 'inside' ? 'inside' : 'outside',
      to: { map: String(p.to_map), x: Number(p.to_x), y: Number(p.to_y) },
    }),
  );
  return {
    id,
    kind,
    width: file.width,
    height: file.height,
    label: props.label as string | undefined,
    building: props.building as string | undefined,
    floor: Number(props.floor ?? 0),
    room: props.room as string | undefined,
    street: kind === 'floor' ? String(props.street) : id,
    offset: kind === 'floor' ? { x: Number(props.street_x), y: Number(props.street_y) } : { x: 0, y: 0 },
    solid: tiles(file, 'solid', () => 1),
    climbable: tiles(file, 'climbable', climbCode),
    walkable: tiles(file, 'collision', () => 1).map((blocked) => 1 - blocked),
    buildings: objects(file, 'buildings'),
    furniture: objects(file, 'furniture'),
    locations: objects(file, 'locations'),
    murals: objects(file, 'murals'),
    links,
    interactables: objects(file, 'interactables'),
    spots: objects(file, 'spots'),
    file,
  };
}

const inside = (map: SideMap, x: number, y: number) =>
  x >= 0 && y >= 0 && x < map.width && y < map.height;

export const isSolid = (map: SideMap, x: number, y: number): boolean =>
  !inside(map, x, y) || map.solid[y * map.width + x] === 1;

export const isWalkable = (map: SideMap, x: number, y: number): boolean =>
  inside(map, x, y) && map.walkable[y * map.width + x] === 1;

export function climbAt(map: SideMap, x: number, y: number): ClimbKind | undefined {
  if (!inside(map, x, y)) return undefined;
  const code = map.climbable[y * map.width + x];
  return code ? CLIMB_KINDS[code - 1] : undefined;
}

/** Walkable and not on a run of stairs or a ladder: somewhere to stand. */
export const isStanding = (map: SideMap, x: number, y: number): boolean =>
  isWalkable(map, x, y) && !climbAt(map, x, y);

/** The top of the solid ground column `x` stands on, under any ledges. */
export function groundRow(map: SideMap, x: number): number {
  let y = map.height;
  while (y > 0 && isSolid(map, x, y - 1)) y--;
  return y;
}

/** The tile a position is read as: W2's `floor(p + 0.5)`. */
export const cellOf = ({ x, y }: { x: number; y: number }): Cell => ({
  x: Math.floor(x + 0.5),
  y: Math.floor(y + 0.5),
});

/** Every street and floor, and how they join. */
export class Village {
  readonly maps: ReadonlyMap<string, SideMap>;
  readonly streets: readonly SideMap[];
  private readonly ends = new Map<string, Link>();
  private readonly floorsByBuilding = new Map<string, SideMap[]>();

  constructor(maps: Iterable<SideMap>) {
    this.maps = new Map([...maps].map((map) => [map.id, map]));
    this.streets = [...this.maps.values()].filter(({ kind }) => kind === 'street');
    for (const map of this.maps.values()) {
      for (const link of map.links) this.ends.set(endKey(map.id, link.x, link.y), link);
      if (map.building) {
        const floors = this.floorsByBuilding.get(map.building) ?? [];
        floors.push(map);
        floors.sort((a, b) => a.floor - b.floor);
        this.floorsByBuilding.set(map.building, floors);
      }
    }
  }

  static read(files: Record<string, TiledFile>): Village {
    return new Village(Object.entries(files).map(([id, file]) => readMap(id, file)));
  }

  map(id: string): SideMap | undefined {
    return this.maps.get(id);
  }

  /** A building's floors, ground floor first. */
  floors(building: string): readonly SideMap[] {
    return this.floorsByBuilding.get(building) ?? [];
  }

  /** The link ending on this tile, which no other link shares. */
  linkAt(map: string, x: number, y: number): Link | undefined {
    return this.ends.get(endKey(map, x, y));
  }

  /** The other end of a link. */
  far(link: Link): Link | undefined {
    return this.linkAt(link.to.map, link.to.x, link.to.y);
  }

  /** Where a position on any map is on its street, in cells. */
  onStreet(position: Position): Cell & { street: string } {
    const map = this.maps.get(position.map ?? '');
    const offset = map?.offset ?? { x: 0, y: 0 };
    return { street: map?.street ?? position.map ?? '', x: position.x + offset.x, y: position.y + offset.y };
  }
}

const endKey = (map: string, x: number, y: number) => `${map}:${x},${y}`;
