import type { Position } from '../net';
import { maps } from './assets';
import { mapOf, objectsOf, propertyOf, tileOf, type MapPosition, type Tile, type TiledMap } from './map';
import type { Direction } from './player';
import { DOOR_FADE_IN_SECONDS, DOOR_FADE_OUT_SECONDS } from './tuning';

export const DOORS_LAYER = 'doors';

export type MapTile = Tile & { map: string };

/** One end of a door: its tile on `map`, the other end, and the way out of it on this side. */
export type Door = MapTile & { id: string; to: MapTile; out: Direction };

const NORTH: Direction = { x: 0, y: -1 };
const SOUTH: Direction = { x: 0, y: 1 };

/** Doors are in buildings' south faces and interiors' front walls, so out is south outside, north in. */
const wayOut = (side: unknown): Direction => (side === 'inside' ? NORTH : SOUTH);

export function doorsOf(id: string, map: TiledMap): Door[] {
  return objectsOf(map, DOORS_LAYER).flatMap((object) => {
    const [toMap, toX, toY] = ['to_map', 'to_x', 'to_y'].map((name) => propertyOf(object, name));
    if (typeof toMap !== 'string' || typeof toX !== 'number' || typeof toY !== 'number') return [];
    return [
      {
        id: object.name,
        map: id,
        x: (object.x ?? 0) / map.tilewidth,
        y: (object.y ?? 0) / map.tileheight,
        to: { map: toMap, x: toX, y: toY },
        out: wayOut(propertyOf(object, 'side')),
      },
    ];
  });
}

const doorsByMap = new Map<string, Door[]>();

/** The doors with an end on a map, once it's loaded. */
export function doorsOn(map: string): readonly Door[] {
  const tiled = maps[map];
  if (!tiled) return [];
  let doors = doorsByMap.get(map);
  if (!doors) doorsByMap.set(map, (doors = doorsOf(map, tiled)));
  return doors;
}

export type Arrival = { position: MapPosition; facing: Direction };

type Passage = { door: Door; fading: 'out' | 'in' };

/** Takes the player through a door they walk onto towards it, once they've stepped off any door. */
export class Doorways {
  /** How far the view has faded to black, 0 to 1. */
  black = 0;
  private readonly doors: (map: string) => readonly Door[];
  private passage?: Passage;
  private armed = false;

  constructor(doors: (map: string) => readonly Door[] = doorsOn) {
    this.doors = doors;
  }

  /** While fading out, the player stays where they are. */
  get holding(): boolean {
    return this.passage?.fading === 'out';
  }

  doorAt(map: string, { x, y }: Tile): Door | undefined {
    return this.doors(map).find((door) => door.x === x && door.y === y);
  }

  /** `ready(map)` says whether the other side can be drawn yet, and may start loading it. */
  update(
    position: Position,
    direction: Direction,
    dt: number,
    ready: (map: string) => boolean,
  ): Arrival | undefined {
    const { passage } = this;
    if (passage?.fading === 'out') {
      this.black = Math.min(1, this.black + dt / DOOR_FADE_OUT_SECONDS);
      if (!ready(passage.door.to.map) || this.black < 1) return undefined;
      passage.fading = 'in';
      return this.arrival(passage.door);
    }
    if (passage?.fading === 'in') {
      this.black = Math.max(0, this.black - dt / DOOR_FADE_IN_SECONDS);
      if (this.black === 0) this.passage = undefined;
    }
    const door = this.doorAt(mapOf(position), tileOf(position));
    if (!door) this.armed = true;
    else if (this.armed && !this.passage && towards(direction, door)) {
      this.armed = false;
      this.passage = { door, fading: 'out' };
      ready(door.to.map);
    }
    return undefined;
  }

  private arrival({ to, out }: Door): Arrival {
    this.armed = false;
    const facing = this.doorAt(to.map, to)?.out ?? { x: -out.x, y: -out.y };
    return { position: { x: to.x, y: to.y, map: to.map }, facing };
  }
}

const towards = (direction: Direction, door: Door) => direction.x * door.out.x + direction.y * door.out.y < 0;
