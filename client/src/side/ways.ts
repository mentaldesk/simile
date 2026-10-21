import { isStanding, type Cell, type ClimbKind, type Link, type SideMap, type Village } from './maps';
import { crossing, type Crossing, type Run } from './runs';

/** Tiles from the middle of a flight's or a ladder's end that climbing it starts from: the whole tile either side. */
export const CLIMB_REACH = 1.5;

/** Where on its map, and how far along the row from the player. */
type Near = { at: Cell; tiles: number };
export type DoorWay = Near & { kind: 'door'; link: Link };
/** To the nearest floor up or down; `car` is the middle of the lift's car along the map. */
export type LiftWay = Near & { kind: 'lift'; up: boolean; link: Link; across: Crossing; car: number };
/** `up` from its foot, down from its top: between floors by a link, or along a run on the map. */
export type ClimbWay = Near & { kind: ClimbKind; up: boolean } & (
    | { link: Link; across: Crossing }
    | { run: Run; distance: number }
  );
export type Way = DoorWay | LiftWay | ClimbWay;

export type Press = 'use' | 'up' | 'down';
export type Key = 'E' | '↑' | '↓';
/** `at` is where on the map its tag goes. */
export type Prompt = { way: Way; keys: Key[]; action: string; at: Cell };

/** Whether walking along the row from `x` gets to `to` without leaving standing cells. */
function walkableBetween(map: SideMap, x: number, to: number, y: number): boolean {
  for (let cx = Math.min(x, to); cx <= Math.max(x, to); cx++) if (!isStanding(map, cx, y)) return false;
  return true;
}

/** From either of its cells, the lift to the next floor up and to the next floor down. */
function liftWays(village: Village, map: SideMap, cell: number, row: number, x: number): LiftWay[] {
  if (!map.links.some((link) => link.kind === 'lift' && link.x === cell && link.y === row)) return [];
  const rides = map.links.flatMap((link) => {
    const across = link.kind === 'lift' && link.y === row ? crossing(village, link) : undefined;
    const floor = village.map(link.to.map)?.floor;
    return across && floor !== undefined ? [{ link, across, floor, car: across.path.points[1].x - map.offset.x }] : [];
  });
  const car = rides.find(({ link }) => link.x === cell)?.car;
  const found: LiftWay[] = [];
  for (const up of [true, false]) {
    const [next] = rides
      .filter((ride) => ride.car === car && ride.floor !== map.floor && ride.floor > map.floor === up)
      .sort((a, b) => (up ? a.floor - b.floor : b.floor - a.floor) || Math.abs(a.link.x - x) - Math.abs(b.link.x - x));
    if (!next) continue;
    const { link, across } = next;
    found.push({ kind: 'lift', up, link, across, car: next.car, at: { x: link.x, y: link.y }, tiles: Math.abs(x - link.x) });
  }
  return found;
}

/** What the player can take from `position` on `map`: a door and the lift from the cell they're on, then stairs and
 * ladders with an end within `CLIMB_REACH` along the row, nearest first. */
export function waysNear(village: Village, map: SideMap, runs: readonly Run[], position: Cell): Way[] {
  const cell = Math.floor(position.x + 0.5);
  const row = Math.round(position.y);
  const onCell: Way[] = [];
  const climbs: Way[] = [];
  const reach = (at: Cell) => {
    const tiles = Math.abs(position.x - at.x);
    return at.y === row && tiles < CLIMB_REACH && walkableBetween(map, cell, at.x, row) ? tiles : undefined;
  };
  for (const link of map.links) {
    const at = { x: link.x, y: link.y };
    if (link.kind === 'door') {
      if (link.x === cell && link.y === row) onCell.push({ kind: 'door', link, at, tiles: Math.abs(position.x - link.x) });
      continue;
    }
    if (link.kind === 'lift') continue;
    const tiles = reach(at);
    const across = tiles === undefined ? undefined : crossing(village, link);
    if (across) climbs.push({ kind: link.kind, up: across.rising, link, across, at, tiles: tiles! });
  }
  onCell.push(...liftWays(village, map, cell, row, position.x));
  for (const run of runs) {
    const ends = [
      { at: run.path.points[0], up: true, distance: 0 },
      { at: run.path.points.at(-1)!, up: false, distance: run.path.total },
    ];
    for (const { at, up, distance } of ends) {
      const tiles = isStanding(map, at.x, at.y) ? reach(at) : undefined;
      if (tiles !== undefined) climbs.push({ kind: run.kind, up, run, distance, at: { x: at.x, y: at.y }, tiles });
    }
  }
  return [...onCell, ...climbs.sort((a, b) => a.tiles - b.tiles)];
}

/** E takes a door on the player's cell, or up does while E is used by something in reach; up and down the rest. */
export function chosen(ways: readonly Way[], press: Press, eTaken = false): Way | undefined {
  const door = ways.find((way) => way.kind === 'door');
  if (press === 'use' || (press === 'up' && eTaken && door)) return door;
  return ways.find((way) => way.kind !== 'door' && way.up === (press === 'up'));
}

function action(village: Village, map: SideMap, way: Way): string {
  if (way.kind === 'door') {
    const there = village.map(way.link.to.map);
    if (there?.kind === 'floor') return 'go in';
    if (map.kind === 'floor') return 'go out';
    return `to ${there?.label ?? way.link.to.map}`;
  }
  if (way.kind === 'lift') return 'lift';
  if (way.kind === 'ladder') return way.up ? 'climb up' : 'climb down';
  if ('run' in way) return way.up ? 'up the steps' : 'down the steps';
  return way.up ? 'upstairs' : 'downstairs';
}

/** A prompt for each way a key takes here, naming its keys. The lift's keys share one, over its car. */
export function prompts(village: Village, map: SideMap, ways: readonly Way[], eTaken = false): Prompt[] {
  const byKey: [Key, Way | undefined][] = [
    ['E', eTaken ? undefined : chosen(ways, 'use')],
    ['↑', chosen(ways, 'up', eTaken)],
    ['↓', chosen(ways, 'down', eTaken)],
  ];
  const found: Prompt[] = [];
  for (const [key, way] of byKey) {
    if (!way) continue;
    const known = found.find((prompt) => prompt.way === way || (way.kind === 'lift' && prompt.way.kind === 'lift'));
    if (known) known.keys.push(key);
    else {
      const at = way.kind === 'lift' ? { x: way.car, y: way.at.y } : way.at;
      found.push({ way, keys: [key], action: action(village, map, way), at });
    }
  }
  return found;
}
