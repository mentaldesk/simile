import { server, type Position, type Wall } from '../net';
import { mapOf } from './map';
import type { Point } from './view';

export const MURAL_REACH_TILES = 3;

type Server = Pick<typeof server, 'on'>;

/** The walls from the latest `murals` message, kept from startup since it comes on connect. */
export class MuralWalls {
  walls: Wall[] = [];
  private readonly listeners = new Set<(walls: Wall[]) => void>();

  constructor(server: Server) {
    server.on('murals', ({ walls }) => {
      this.walls = walls;
      for (const listener of this.listeners) listener(walls);
    });
  }

  wall(id: string): Wall | undefined {
    return this.walls.find((wall) => wall.id === id);
  }

  onChange(listener: (walls: Wall[]) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }
}

export const muralWalls = new MuralWalls(server);

/** Tiles along the street from the player to the nearer end of the wall, which faces the camera. */
export function tilesToWall(wall: Wall, position: Position): number {
  const along = position.x + 0.5;
  return Math.max(wall.x - along, 0, along - (wall.x + wall.width));
}

/** The nearest painted wall within reach along the player's street. */
export function wallNear(walls: readonly Wall[], position: Position | undefined): Wall | undefined {
  if (!position) return undefined;
  let nearest: { wall: Wall; distance: number } | undefined;
  for (const wall of walls) {
    if (!wall.mural || wall.map !== mapOf(position)) continue;
    const distance = tilesToWall(wall, position);
    if (distance > MURAL_REACH_TILES) continue;
    if (!nearest || distance < nearest.distance) nearest = { wall, distance };
  }
  return nearest?.wall;
}

/** What the mural panel needs from the scene drawing the murals. */
export interface MuralView {
  /** The wall drawn at a game-canvas point. */
  wallAt(point: Point): string | undefined;
}

let registered: MuralView | undefined;

export function setMuralView(view: MuralView): () => void {
  registered = view;
  return () => {
    if (registered === view) registered = undefined;
  };
}

export const muralView = (): MuralView | undefined => registered;
