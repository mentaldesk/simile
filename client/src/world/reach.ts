import type { Position, Wall } from '../net';
import { maps } from './assets';
import { interactableAt, type Interactable } from './interactables';
import { mapOf } from './map';
import { muralView, muralWalls, tilesToWall, wallNear } from './murals';
import { terminalAt, terminalsOn, type Terminal } from './terminals';

/** Something E uses, `tiles` along the street from the player. */
export type Reachable =
  | { kind: 'terminal'; tiles: number; terminal: Terminal }
  | { kind: 'counter' | 'painting'; tiles: number; interactable: Interactable }
  | { kind: 'mural'; tiles: number; wall: Wall };

export type Reachables = {
  terminals: readonly Terminal[];
  walls(): readonly Wall[];
  interactableAt(map: string, position: Position): Interactable | undefined;
};

/** Murals only count while a scene draws them, as for the mural panel. */
export const reachables: Reachables = {
  terminals: terminalsOn(maps),
  walls: () => (muralView() ? muralWalls.walls : []),
  interactableAt,
};

const isUsed = (kind: string): kind is 'counter' | 'painting' => kind === 'counter' || kind === 'painting';

/** What E can use where the player stands, nearest first. */
export function inReach(position: Position | undefined, from: Reachables = reachables): Reachable[] {
  if (!position) return [];
  const along = position.x + 0.5;
  const found: Reachable[] = [];
  const terminal = terminalAt(from.terminals, position);
  if (terminal) {
    const tiles = Math.max(terminal.x - along, 0, along - (terminal.x + terminal.width));
    found.push({ kind: 'terminal', tiles, terminal });
  }
  const interactable = from.interactableAt(mapOf(position), position);
  if (interactable && isUsed(interactable.kind)) {
    const tiles = Math.min(...interactable.stand.map(({ x }) => Math.abs(x + 0.5 - along)));
    found.push({ kind: interactable.kind, tiles, interactable });
  }
  const wall = wallNear(from.walls(), position);
  if (wall) found.push({ kind: 'mural', tiles: tilesToWall(wall, position), wall });
  return found.sort((a, b) => a.tiles - b.tiles);
}

/** What E uses: a door, stairs, a ladder or a lift only when there's nothing. */
export const usedByE = (position: Position | undefined, from?: Reachables): Reachable | undefined =>
  inReach(position, from)[0];

/** The keys that take a door, stairs, a ladder or a lift, what it does, and a game-canvas point just above it. */
export type WayPrompt = { keys: readonly string[]; action: string; x: number; y: number };

type WayPrompts = (eTaken: boolean) => readonly WayPrompt[];

let waysHere: WayPrompts | undefined;

/** The world scene's prompts for the ways the player can take from where they stand. */
export function setWayPrompts(prompts: WayPrompts): () => void {
  waysHere = prompts;
  return () => {
    if (waysHere === prompts) waysHere = undefined;
  };
}

/** `eTaken` while E uses something in reach, so it's left off. */
export const wayPrompts = (eTaken = false): readonly WayPrompt[] => waysHere?.(eTaken) ?? [];
