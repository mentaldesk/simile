import { playerState, type Buyer, type Corpse, type MapTile, type Pile, type PlayerStateMessage, type Position, type Wall } from '../net';
import { maps } from './assets';
import { trades } from './buyers';
import { sideClock } from '../side/clock';
import { clueInReach, clues, type Clue } from './clues';
import { interactableAt, type Interactable } from './interactables';
import { jacked, leadsAway, liftOpen } from './jacks';
import { mapOf } from './map';
import { muralView, muralWalls, tilesToWall, wallNear } from './murals';
import { searches } from './searchables';
import { terminalAt, terminalsOn, type Terminal } from './terminals';

/** The corpse E takes from, as a pile since E is `pick_up` for both, whether it looks like E can take anything, and how many more like it lie on its tile. */
export type Salvage = { corpse: Corpse; others: number; takes: boolean };

/** Something E uses, V looks at or T orders at, `tiles` along the street from the player. */
export type Reachable =
  | { kind: 'terminal'; tiles: number; terminal: Terminal }
  | { kind: 'counter' | 'painting' | 'jack' | 'searchable'; tiles: number; interactable: Interactable }
  | { kind: 'mural'; tiles: number; wall: Wall }
  | { kind: 'pile'; tiles: number; pile: Pile; salvage?: Salvage }
  | { kind: 'buyer'; tiles: number; buyer: Buyer }
  | { kind: 'clinic'; tiles: number; buyer: Buyer }
  | { kind: 'clue'; tiles: number; clue: Clue }
  | { kind: 'bed'; tiles: number; bed: MapTile };

export type Reachables = {
  terminals: readonly Terminal[];
  walls(): readonly Wall[];
  interactableAt(map: string, position: Position): Interactable | undefined;
  piles(): readonly Pile[];
  corpses?: () => readonly Corpse[];
  /** What more they can carry, in kg. */
  room?: () => number;
  buyer(): Buyer | undefined;
  clues: readonly Clue[];
  /** Whether the datajack is fitted. */
  jacked?: () => boolean;
  /** Whether the lift goes down without it. */
  liftOpen?: () => boolean;
  /** Whether a link leaves from the jack's stand tile, for E to take once it works. */
  leadsAway?: (jack: Interactable) => boolean;
  /** The interactables the player has searched, by id. */
  searched?: () => readonly string[];
  /** Their bed where they stand, while they could rest in it. */
  bed?: () => MapTile | undefined;
};

/** When a rest sleeps until morning: from 21:00, the earliest bedtime any resident can have, as the server's `NIGHT_STARTS`, until 06:00. */
export const NIGHT = { from: 21, until: 6 };

export function atNight(hour: number): boolean {
  return hour >= NIGHT.from || hour < NIGHT.until;
}

/** Their bed where they stand, unless they're resting already, or in the daytime well, infected or starving, when the server ignores `rest`. */
export function restsAt(state: PlayerStateMessage | undefined, hour = sideClock.hour()): MapTile | undefined {
  if (!state?.bed || state.resting) return undefined;
  if (atNight(hour)) return state.bed;
  if ((state.player.health ?? 1) >= 1 || state.player.hunger >= 1) return undefined;
  return state.player.effects?.some(({ kind }) => kind === 'infection') ? undefined : state.bed;
}

/** Murals only count while a scene draws them, as for the mural panel. */
export const reachables: Reachables = {
  terminals: terminalsOn(maps),
  walls: () => (muralView() ? muralWalls.walls : []),
  interactableAt,
  piles: () => [...(playerState.latest?.player.left ?? []), ...(playerState.latest?.piles ?? [])],
  corpses: () => playerState.latest?.player.corpses ?? [],
  room: () => {
    const player = playerState.latest?.player;
    return player ? player.items.reduce((room, { weight, amount = 1 }) => room - weight * amount, player.carry_limit) : Infinity;
  },
  buyer: () => playerState.latest?.buyer ?? undefined,
  clues,
  jacked: () => jacked(playerState.latest?.player.body),
  liftOpen: () => liftOpen(playerState.latest?.player),
  leadsAway,
  searched: () => playerState.latest?.player.searched ?? [],
  bed: () => restsAt(playerState.latest),
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

const holds = ({ money, items, bionics }: Corpse) => money > 0 || items.length > 0 || bionics.length > 0;

/** Whether E looks able to take anything from it. Only the server knows what a bionic weighs, so any bionic counts. */
const takesFrom = ({ money, items, bionics }: Corpse, room: number) =>
  money > 0 || bionics.length > 0 || items.some(({ weight, amount = 1 }) => weight * amount <= room + 1e-9);

/** The nearest corpse on this map within reach that E can take something from, the oldest on a tie, as the server takes it, or else the nearest that holds anything. */
export function corpseInReach(position: Position, corpses: readonly Corpse[], room = Infinity): { salvage: Salvage; tiles: number } | undefined {
  const near = corpses
    .filter((corpse) => holds(corpse) && corpse.at.map === mapOf(position))
    .map((corpse) => ({ corpse, tiles: Math.hypot(corpse.at.x - position.x, corpse.at.y - position.y) }))
    .filter(({ tiles }) => tiles <= PICK_UP_TILES);
  if (!near.length) return undefined;
  const taking = near.filter(({ corpse }) => takesFrom(corpse, room));
  const pool = taking.length ? taking : near;
  const best = pool.reduce((nearest, next) => (next.tiles < nearest.tiles ? next : nearest));
  const { x, y } = best.corpse.at;
  const others = pool.filter(({ corpse }) => corpse.at.x === x && corpse.at.y === y).length - 1;
  return { salvage: { corpse: best.corpse, others, takes: taking.length > 0 }, tiles: best.tiles };
}

/** These are 0 tiles away from anywhere they're offered, and would hide a body E can take from for good. */
const ALWAYS_NEAR: readonly Reachable['kind'][] = ['terminal', 'clinic', 'buyer', 'bed'];

const isUsed = (kind: string): kind is 'counter' | 'painting' | 'jack' =>
  kind === 'counter' || kind === 'painting' || kind === 'jack';

/** A jack is used with E, unless it works and a link leaves from it, which E takes instead. */
export const opens = (from: Reachables, jack: Interactable) => (!!from.jacked?.() || !!from.liftOpen?.()) && !!from.leadsAway?.(jack);

/** What E can use, V look at or T order at where the player stands, nearest first. */
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
  const bed = from.bed?.();
  if (bed) found.push({ kind: 'bed', tiles: 0, bed });
  const sorted = found.sort((a, b) => a.tiles - b.tiles);
  const body = corpseInReach(position, from.corpses?.() ?? [], from.room?.());
  if (!body || (!body.salvage.takes && interactable?.kind === 'machine')) return sorted;
  const after = sorted.findIndex(({ kind, tiles }) => tiles > body.tiles || (body.salvage.takes && ALWAYS_NEAR.includes(kind)));
  sorted.splice(after < 0 ? sorted.length : after, 0, { kind: 'pile', pile: body.salvage.corpse, ...body });
  return sorted;
}

const keyFor = ({ kind }: Reachable): 'E' | 'T' | 'V' =>
  kind === 'mural' || kind === 'painting' ? 'V' : kind === 'counter' ? 'T' : 'E';

/** What E uses off a door's cell, where E takes the door. */
export const usedByE = (position: Position | undefined, from?: Reachables): Reachable | undefined =>
  inReach(position, from).find((reachable) => keyFor(reachable) === 'E');

/** The mural or painting V looks at. */
export const lookedAtByV = (position: Position | undefined, from?: Reachables): Reachable | undefined =>
  inReach(position, from).find((reachable) => keyFor(reachable) === 'V');

/** The counter T orders at, from whoever serves there. */
export const orderedAtByT = (position: Position | undefined, from?: Reachables): Interactable | undefined => {
  const counter = inReach(position, from).find((reachable) => keyFor(reachable) === 'T');
  return counter?.kind === 'counter' ? counter.interactable : undefined;
};

/** The keys that take a door, stairs, a ladder or the lift, what it does, and a game-canvas point just above it. */
export type WayPrompt = { keys: readonly string[]; action: string; x: number; y: number };

type WayPrompts = () => readonly WayPrompt[];

let waysHere: WayPrompts | undefined;

/** The world scene's prompts for the ways the player can take from where they stand. */
export function setWayPrompts(prompts: WayPrompts): () => void {
  waysHere = prompts;
  return () => {
    if (waysHere === prompts) waysHere = undefined;
  };
}

export const wayPrompts = (): readonly WayPrompt[] => waysHere?.() ?? [];

/** Whether E takes a door from where the player stands. */
export const doorOnE = (ways: readonly WayPrompt[]): boolean => ways.some(({ keys }) => keys.includes('E'));

/** What E uses here: nothing on a door's cell, where E takes the door. */
export const eUse = (position: Position | undefined, ways: readonly WayPrompt[], from?: Reachables): Reachable | undefined =>
  doorOnE(ways) ? undefined : usedByE(position, from);
