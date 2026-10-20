import { isStanding, type Cell, type ClimbKind, type Link, type SideMap, type Village } from './maps';
import { crossing, type Crossing, type Run } from './runs';

/** Tiles either side of a flight's or a ladder's end that climbing it starts from. */
export const CLIMB_REACH = 1;

/** Where on its map, and how far along the row from the player. */
type Near = { at: Cell; tiles: number };
export type DoorWay = Near & { kind: 'door'; link: Link };
export type LiftWay = Near & { kind: 'lift'; link: Link; across: Crossing };
/** `up` from its foot, down from its top: between floors by a link, or along a run on the map. */
export type ClimbWay = Near & { kind: ClimbKind; up: boolean } & (
    | { link: Link; across: Crossing }
    | { run: Run; distance: number }
  );
export type Way = DoorWay | LiftWay | ClimbWay;

export type Press = 'use' | 'up' | 'down';
export type Key = 'E' | '↑' | '↓';
export type Prompt = { way: Way; keys: Key[]; action: string };

/** Whether walking along the row from `x` gets to `to` without leaving standing cells. */
function walkableBetween(map: SideMap, x: number, to: number, y: number): boolean {
  for (let cx = Math.min(x, to); cx <= Math.max(x, to); cx++) if (!isStanding(map, cx, y)) return false;
  return true;
}

/** What the player can take from `position` on `map`, nearest first: a door or a lift on the cell they're on,
 * or stairs and ladders with an end within `CLIMB_REACH` along the row. */
export function waysNear(village: Village, map: SideMap, runs: readonly Run[], position: Cell): Way[] {
  const cell = Math.floor(position.x + 0.5);
  const row = Math.round(position.y);
  const found: Way[] = [];
  const reach = (at: Cell) => {
    const tiles = Math.abs(position.x - at.x);
    return at.y === row && tiles <= CLIMB_REACH && walkableBetween(map, cell, at.x, row) ? tiles : undefined;
  };
  for (const link of map.links) {
    const at = { x: link.x, y: link.y };
    if (link.kind === 'door' || link.kind === 'lift') {
      if (link.x !== cell || link.y !== row) continue;
      const tiles = Math.abs(position.x - link.x);
      if (link.kind === 'door') found.push({ kind: 'door', link, at, tiles });
      else {
        const across = crossing(village, link);
        if (across) found.push({ kind: 'lift', link, across, at, tiles });
      }
      continue;
    }
    const tiles = reach(at);
    const across = tiles === undefined ? undefined : crossing(village, link);
    if (across) found.push({ kind: link.kind, up: across.rising, link, across, at, tiles: tiles! });
  }
  for (const run of runs) {
    const ends = [
      { at: run.path.points[0], up: true, distance: 0 },
      { at: run.path.points.at(-1)!, up: false, distance: run.path.total },
    ];
    for (const { at, up, distance } of ends) {
      const tiles = isStanding(map, at.x, at.y) ? reach(at) : undefined;
      if (tiles !== undefined) found.push({ kind: run.kind, up, run, distance, at: { x: at.x, y: at.y }, tiles });
    }
  }
  return found.sort((a, b) => a.tiles - b.tiles);
}

/** E takes the nearest; up a door on this cell, or else the nearest way up; down the front door from inside, or
 * else the nearest way down. A lift is only E's. */
export function chosen(ways: readonly Way[], press: Press, map: SideMap): Way | undefined {
  if (press === 'use') return ways[0];
  const door = ways.find((way): way is DoorWay => way.kind === 'door');
  if (press === 'up' && door) return door;
  if (press === 'down' && door?.link.side === 'inside' && map.kind === 'floor') return door;
  return ways.find((way) => way.kind !== 'door' && way.kind !== 'lift' && way.up === (press === 'up'));
}

const FLOORS = ['the ground floor', 'the first floor', 'the second floor', 'the third floor'];

const floorName = (floor: number) => FLOORS[floor] ?? `floor ${floor}`;

function action(village: Village, map: SideMap, way: Way): string {
  if (way.kind === 'door') {
    const there = village.map(way.link.to.map);
    if (there?.kind === 'floor') return 'go in';
    if (map.kind === 'floor') return 'go out';
    return `to ${there?.label ?? way.link.to.map}`;
  }
  if (way.kind === 'lift') return `lift to ${floorName(village.map(way.link.to.map)?.floor ?? 0)}`;
  if (way.kind === 'ladder') return way.up ? 'climb up' : 'climb down';
  if ('run' in way) return way.up ? 'up the steps' : 'down the steps';
  return way.up ? 'upstairs' : 'downstairs';
}

/** A prompt for each way a key takes here, naming the keys: E's unless something in reach takes E. */
export function prompts(village: Village, map: SideMap, ways: readonly Way[], eTaken = false): Prompt[] {
  const byKey: [Key, Way | undefined][] = [
    ['E', eTaken ? undefined : chosen(ways, 'use', map)],
    ['↑', chosen(ways, 'up', map)],
    ['↓', chosen(ways, 'down', map)],
  ];
  const found: Prompt[] = [];
  for (const [key, way] of byKey) {
    if (!way || (key === '↓' && way.kind === 'door')) continue;
    const known = found.find((prompt) => prompt.way === way);
    if (known) known.keys.push(key);
    else found.push({ way, keys: [key], action: action(village, map, way) });
  }
  return found;
}
