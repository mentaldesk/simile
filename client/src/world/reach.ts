import { playerState, type Buyer, type Pile, type Position, type Wall } from '../net';
import { maps } from './assets';
import { trades } from './buyers';
import { clueInReach, clues, type Clue } from './clues';
import { interactableAt, type Interactable } from './interactables';
import { jacked, leadsAway } from './jacks';
import { mapOf } from './map';
import { muralView, muralWalls, tilesToWall, wallNear } from './murals';
import { searches } from './searchables';
import { terminalAt, terminalsOn, type Terminal } from './terminals';

/** Something E uses, `tiles` along the street from the player. */
export type Reachable =
  | { kind: 'terminal'; tiles: number; terminal: Terminal }
  | { kind: 'counter' | 'painting' | 'jack' | 'searchable'; tiles: number; interactable: Interactable }
  | { kind: 'mural'; tiles: number; wall: Wall }
  | { kind: 'pile'; tiles: number; pile: Pile }
  | { kind: 'buyer'; tiles: number; buyer: Buyer }
  | { kind: 'clinic'; tiles: number; buyer: Buyer }
  | { kind: 'clue'; tiles: number; clue: Clue };

export type Reachables = {
  terminals: readonly Terminal[];
  walls(): readonly Wall[];
  interactableAt(map: string, position: Position): Interactable | undefined;
  piles(): readonly Pile[];
  buyer(): Buyer | undefined;
  clues: readonly Clue[];
  /** Whether the datajack is fitted. */
  jacked?: () => boolean;
  /** Whether a link leaves from the jack's stand tile, for E to take once it works. */
  leadsAway?: (jack: Interactable) => boolean;
  /** The interactables the player has searched, by id. */
  searched?: () => readonly string[];
};

/** Murals only count while a scene draws them, as for the mural panel. */
export const reachables: Reachables = {
  terminals: terminalsOn(maps),
  walls: () => (muralView() ? muralWalls.walls : []),
  interactableAt,
  piles: () => [...(playerState.latest?.player.left ?? []), ...(playerState.latest?.piles ?? [])],
  buyer: () => playerState.latest?.buyer ?? undefined,
  clues,
  jacked: () => jacked(playerState.latest?.player.body),
  leadsAway,
  searched: () => playerState.latest?.player.searched ?? [],
};

/** Inside the server's reach of a tile and a half, so a pick-up E offers still reaches. */
export const PICK_UP_TILES = 1;

/** The nearest pile on this map within reach of where they stand: one they left, or one lying about. */
export function pileInReach(position: Position, piles: readonly Pile[]): { pile: Pile; tiles: number } | undefined {
  let best: { pile: Pile; tiles: number } | undefined;
  for (const pile of piles) {
    if (pile.at.map !== mapOf(position)) continue;
    const tiles = Math.hypot(pile.at.x - position.x, pile.at.y - position.y);
    if (tiles <= PICK_UP_TILES && (!best || tiles < best.tiles)) best = { pile, tiles };
  }
  return best;
}

const isUsed = (kind: string): kind is 'counter' | 'painting' | 'jack' =>
  kind === 'counter' || kind === 'painting' || kind === 'jack';

/** A jack is used with E, unless it works and a link leaves from it, which E takes instead. */
const opens = (from: Reachables, jack: Interactable) => !!from.jacked?.() && !!from.leadsAway?.(jack);

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
  if (interactable && searches(interactable, from.searched?.() ?? [], !!from.jacked?.())) {
    found.push({ kind: 'searchable', tiles: -1, interactable });
  } else if (interactable && isUsed(interactable.kind) && !(interactable.kind === 'jack' && opens(from, interactable))) {
    const tiles = Math.min(...interactable.stand.map(({ x }) => Math.abs(x + 0.5 - along)));
    found.push({ kind: interactable.kind, tiles, interactable });
  }
  const wall = wallNear(from.walls(), position);
  if (wall) found.push({ kind: 'mural', tiles: tilesToWall(wall, position), wall });
  const pile = pileInReach(position, from.piles());
  if (pile) found.push({ kind: 'pile', ...pile });
  const buyer = from.buyer();
  if (buyer && trades(buyer)) found.push({ kind: 'clinic', tiles: 0, buyer });
  else if (buyer && Object.keys(buyer.prices).length) found.push({ kind: 'buyer', tiles: 0, buyer });
  const clue = clueInReach(position, from.clues);
  if (clue) found.push({ kind: 'clue', ...clue });
  return found.sort((a, b) => a.tiles - b.tiles);
}

/** What E uses: a door only when there's nothing. */
export const usedByE = (position: Position | undefined, from?: Reachables): Reachable | undefined =>
  inReach(position, from)[0];

/** The keys that take a door, stairs, a ladder or the lift, what it does, and a game-canvas point just above it. */
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

/** `eTaken` while E uses something in reach, so up takes a door instead. */
export const wayPrompts = (eTaken = false): readonly WayPrompt[] => waysHere?.(eTaken) ?? [];
