import { climbAt, isWalkable, type Cell, type ClimbKind, type Link, type SideMap, type Village } from './maps';

export type Path = { points: readonly Cell[]; lengths: readonly number[]; total: number };

export function pathOf(points: readonly Cell[]): Path {
  const lengths = points.slice(1).map((point, i) => Math.hypot(point.x - points[i].x, point.y - points[i].y));
  return { points, lengths, total: lengths.reduce((sum, length) => sum + length, 0) };
}

/** Clamped to the path's ends, written into `out`. */
export function pointAlong(path: Path, distance: number, out: Cell): Cell {
  const { points, lengths } = path;
  let left = Math.min(Math.max(distance, 0), path.total);
  for (let i = 0; i < lengths.length; i++) {
    if (left <= lengths[i] || i === lengths.length - 1) {
      const t = lengths[i] === 0 ? 1 : Math.min(left / lengths[i], 1);
      out.x = points[i].x + (points[i + 1].x - points[i].x) * t;
      out.y = points[i].y + (points[i + 1].y - points[i].y) * t;
      return out;
    }
    left -= lengths[i];
  }
  out.x = points[0].x;
  out.y = points[0].y;
  return out;
}

export function distanceTo(path: Path, point: Cell): number {
  let best = Infinity;
  let at = 0;
  let start = 0;
  for (let i = 0; i < path.lengths.length; i++) {
    const [a, b] = [path.points[i], path.points[i + 1]];
    const length = path.lengths[i];
    const t = length === 0 ? 0 : ((point.x - a.x) * (b.x - a.x) + (point.y - a.y) * (b.y - a.y)) / length ** 2;
    const clamped = Math.min(Math.max(t, 0), 1);
    const gap = Math.hypot(a.x + (b.x - a.x) * clamped - point.x, a.y + (b.y - a.y) * clamped - point.y);
    if (gap < best) {
      best = gap;
      at = start + clamped * length;
    }
    start += length;
  }
  return at;
}

/** Bottom first, to the cell stepped off onto at the top. */
export type Run = { kind: ClimbKind; map: string; path: Path };

function groups(map: SideMap, kind: ClimbKind, joined: (a: Cell, b: Cell) => boolean): Cell[][] {
  const cells: Cell[] = [];
  for (let y = 0; y < map.height; y++) {
    for (let x = 0; x < map.width; x++) if (climbAt(map, x, y) === kind) cells.push({ x, y });
  }
  const found: Cell[][] = [];
  for (const cell of cells) {
    const touching = found.filter((group) => group.some((other) => joined(cell, other)));
    const merged = [cell, ...touching.flat()];
    for (const group of touching) found.splice(found.indexOf(group), 1);
    found.push(merged);
  }
  return found.map((group) => group.sort((a, b) => b.y - a.y));
}

function ladderRun(map: SideMap, rungs: Cell[]): Run | undefined {
  const [bottom, top] = [rungs[0], rungs.at(-1)!];
  const foot = { x: bottom.x, y: bottom.y + 1 };
  if (!isWalkable(map, foot.x, foot.y)) return undefined;
  const ledge = [1, -1].map((dx) => ({ x: top.x + dx, y: top.y })).find(({ x, y }) => isWalkable(map, x, y));
  return { kind: 'ladder', map: map.id, path: pathOf([foot, ...rungs, ...(ledge ? [ledge] : [])]) };
}

function stairsRun(map: SideMap, stairs: Cell[]): Run | undefined {
  const [bottom, top] = [stairs[0], stairs.at(-1)!];
  const rises = stairs.length > 1 ? [Math.sign(top.x - bottom.x)] : [1, -1];
  for (const rise of rises) {
    const foot = { x: bottom.x - rise, y: bottom.y + 1 };
    const head = { x: top.x + rise, y: top.y - 1 };
    if (isWalkable(map, foot.x, foot.y) && isWalkable(map, head.x, head.y)) {
      return { kind: 'stairs', map: map.id, path: pathOf([foot, ...stairs, head]) };
    }
  }
  return undefined;
}

export function climbRuns(map: SideMap): Run[] {
  const ladders = groups(map, 'ladder', (a, b) => a.x === b.x && Math.abs(a.y - b.y) === 1);
  const stairs = groups(map, 'stairs', (a, b) => Math.abs(a.x - b.x) === 1 && Math.abs(a.y - b.y) === 1);
  return [
    ...ladders.map((rungs) => ladderRun(map, rungs)),
    ...stairs.map((flight) => stairsRun(map, flight)),
  ].filter((run): run is Run => run !== undefined);
}

/** In street cells, as walked from `from` to `to`. */
export type Crossing = { kind: Exclude<Link['kind'], 'door'>; from: Link; to: Link; path: Path; rising: boolean };

function carX(map: SideMap, end: Cell): number {
  const cars = map.furniture.filter(({ name }) => name === 'lift');
  const nearest = cars.sort((a, b) => Math.abs(a.x - end.x) - Math.abs(b.x - end.x))[0];
  return nearest ? nearest.x + (nearest.w - 1) / 2 : end.x;
}

/** Undefined for a door or a link to a missing map. */
export function crossing(village: Village, from: Link): Crossing | undefined {
  if (from.kind === 'door') return undefined;
  const to = village.far(from);
  const [here, there] = [village.map(from.map), village.map(from.to.map)];
  if (!to || !here || !there) return undefined;
  const a = village.onStreet({ ...from, map: from.map });
  const b = village.onStreet({ ...to, map: to.map });
  const start = { x: a.x, y: a.y };
  const end = { x: b.x, y: b.y };
  let points: Cell[] = [start, end];
  if (from.kind === 'lift') {
    const x = here.offset.x + carX(here, from);
    points = [start, { x, y: start.y }, { x, y: end.y }, end];
  }
  return { kind: from.kind, from, to, path: pathOf(points), rising: end.y < start.y };
}
