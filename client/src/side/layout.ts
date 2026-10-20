import { groundRow, isSolid, type Cell, type Placed, type SideMap } from './maps';
import type { Piece, SceneryManifest } from './scenery';

/** The manifest's `ppm`: world px are the pieces' own. */
export const PPM = 120;
export const TILE_M = 1.1;
export const TILE = TILE_M * PPM;
export const STOREY_M = 4.4;
/** content/dolls/README.md's street height. */
export const DOLL_M = 2.04;

/** The pavement's far edge, above the feet line. */
export const GROUND_LIFT_M = 0.35;
export const FURNITURE_DROP_M = 0.06;
export const STRETCH_FILL = 0.96;
export const STRETCH_CAP = 0.15;

/** The middle of its cell. */
export const xOf = (x: number): number => (x + 0.5) * TILE;
/** The bottom of its cell. */
export const feetOf = (y: number): number => (y + 1) * TILE;

export type Placement = { x: number; y: number; originX: number; originY: number };

export function frontPlacement(building: Placed, piece: Piece): Placement {
  const [originX, originY] = piece.anchor ?? [0.5, 1];
  return { x: (building.x + building.w / 2) * TILE, y: (building.y + building.h) * TILE, originX, originY };
}

/** In the front's px from its top: what a dollhouse keeps. */
export function roofHeight(piece: Piece, ppm = PPM): number {
  const [, anchorY] = piece.anchor ?? [0.5, 1];
  return Math.max(1, Math.round(piece.size[1] * anchorY - (piece.eaves ?? 0) * ppm));
}

export type Rect = { x: number; y: number; width: number; height: number };

export type WallSpan = Cell & { width: number; bottom: number; top: number };

/** Left blank on the front from `bottom` to `top` storeys, up to the eaves. */
export function muralRect(wall: WallSpan, eaves = Infinity): Rect {
  const base = feetOf(wall.y);
  const top = Math.min(wall.top * STOREY_M, eaves) * PPM;
  const bottom = wall.bottom * STOREY_M * PPM;
  return { x: wall.x * TILE, y: base - top, width: wall.width * TILE, height: Math.max(0, top - bottom) };
}

/** Hung on the wall if it's above a room's standing row. */
export function furniturePlacement(item: Placed, map: SideMap): Placement {
  const x = (map.offset.x + item.x + item.w / 2) * TILE;
  if (map.kind === 'floor' && item.y + item.h <= 1) {
    return { x, y: (map.offset.y + item.y + item.h / 2) * TILE, originX: 0.5, originY: 0.5 };
  }
  return { x, y: (map.offset.y + item.y + item.h) * TILE + FURNITURE_DROP_M * PPM, originX: 0.5, originY: 1 };
}

export const stretchWidth = (item: Placed): number => Math.round(item.w * TILE * STRETCH_FILL);

export function stretchParts(width: number, sourceWidth: number, cap = STRETCH_CAP) {
  const end = Math.round(sourceWidth * cap);
  const middle = Math.max(1, sourceWidth - 2 * end);
  const fill = Math.max(0, width - 2 * end);
  return { end, middle, fill, repeats: Math.ceil(fill / middle) };
}

export type GroundRun = { key: string; x0: number; x1: number; row: number };

export function streetRow(map: SideMap): number {
  const counts = new Map<number, number>();
  for (let x = 0; x < map.width; x++) {
    const row = groundRow(map, x);
    counts.set(row, (counts.get(row) ?? 0) + 1);
  }
  return [...counts].sort((a, b) => b[1] - a[1] || a[0] - b[0])[0][0];
}

export function groundRuns(map: SideMap, manifest: SceneryManifest): GroundRun[] {
  const row = streetRow(map);
  const street = manifest.streets[map.id]?.ground;
  const keyAt = (x: number) => {
    if (groundRow(map, x) > row) return manifest.grounds.riverside;
    for (const place of ['square', 'park']) {
      const area = map.locations.find(({ name }) => name === place);
      if (area && area.x <= x && x < area.x + area.w) return manifest.grounds[place];
    }
    return street;
  };
  const runs: GroundRun[] = [];
  for (let x = 0; x < map.width; x++) {
    const key = keyAt(x);
    const at = groundRow(map, x);
    const last = runs.at(-1);
    if (last && last.key === key && last.row === at) last.x1 = x + 1;
    else runs.push({ key, x0: x, x1: x + 1, row: at });
  }
  return runs;
}

export type Ledge = { x0: number; x1: number; row: number };

export function ledges(map: SideMap): Ledge[] {
  const below = streetRow(map);
  const found: Ledge[] = [];
  for (let row = 0; row < below; row++) {
    for (let x = 0; x < map.width; x++) {
      if (!isSolid(map, x, row) || row >= groundRow(map, x)) continue;
      const last = found.at(-1);
      if (last && last.row === row && last.x1 === x) last.x1 = x + 1;
      else found.push({ x0: x, x1: x + 1, row });
    }
  }
  return found;
}

export type Dollhouse = {
  left: number;
  right: number;
  top: number;
  ground: number;
  floors: { map: SideMap; floorLine: number; ceiling: number }[];
};

export function dollhouse(building: Placed, floors: readonly SideMap[]): Dollhouse {
  const top = building.y * TILE;
  const lines = floors.map((map) => (map.offset.y + 3) * TILE);
  return {
    left: building.x * TILE,
    right: (building.x + building.w) * TILE,
    top,
    ground: (building.y + building.h) * TILE,
    floors: floors.map((map, i) => ({ map, floorLine: lines[i], ceiling: lines[i + 1] ?? top })),
  };
}
