import type { Position } from '../net';
import type { CollisionMap } from './map';
import { facingFor, type Body, type Facing } from './motion';
import { PLAYER_SPEED } from './tuning';

/** The part of the player's tile that collides: around the feet, which are on the tile's bottom edge. */
export const FOOTPRINT = { left: 0.25, right: 0.75, top: 0.65, bottom: 1 };

type Span = [first: number, last: number];

const tilesUnder = (from: number, to: number): Span => [Math.floor(from), Math.ceil(to) - 1];

function anyBlocked(map: CollisionMap, columns: Span, rows: Span): boolean {
  for (let y = rows[0]; y <= rows[1]; y++) {
    for (let x = columns[0]; x <= columns[1]; x++) if (map.blocks(x, y)) return true;
  }
  return false;
}

/** Moves by less than a tile, one axis at a time, stopping flush against blocked tiles. */
export function walk(map: CollisionMap, from: Position, dx: number, dy: number): Position {
  let { x, y } = from;
  const rows = tilesUnder(y + FOOTPRINT.top, y + FOOTPRINT.bottom);
  if (dx > 0) {
    const column = Math.ceil(x + dx + FOOTPRINT.right) - 1;
    x = anyBlocked(map, [column, column], rows) ? Math.max(x, column - FOOTPRINT.right) : x + dx;
  } else if (dx < 0) {
    const column = Math.floor(x + dx + FOOTPRINT.left);
    x = anyBlocked(map, [column, column], rows) ? Math.min(x, column + 1 - FOOTPRINT.left) : x + dx;
  }
  const columns = tilesUnder(x + FOOTPRINT.left, x + FOOTPRINT.right);
  if (dy > 0) {
    const row = Math.ceil(y + dy + FOOTPRINT.bottom) - 1;
    y = anyBlocked(map, columns, [row, row]) ? Math.max(y, row - FOOTPRINT.bottom) : y + dy;
  } else if (dy < 0) {
    const row = Math.floor(y + dy + FOOTPRINT.top);
    y = anyBlocked(map, columns, [row, row]) ? Math.min(y, row + 1 - FOOTPRINT.top) : y + dy;
  }
  return { x, y };
}

export type Direction = { x: number; y: number };

export class Player implements Body {
  position: Position;
  facing: Facing = 'down';
  walking = false;

  constructor(position: Position) {
    this.position = { ...position };
  }

  place(position: Position): void {
    this.position = { ...position };
  }

  move(direction: Direction, dt: number, map: CollisionMap, speed = PLAYER_SPEED): void {
    const length = Math.hypot(direction.x, direction.y);
    if (length === 0) {
      this.walking = false;
      return;
    }
    this.facing = facingFor(direction.x, direction.y, this.facing);
    const step = (speed * dt) / length;
    const next = walk(map, this.position, direction.x * step, direction.y * step);
    this.walking = next.x !== this.position.x || next.y !== this.position.y;
    this.position = next;
  }
}
