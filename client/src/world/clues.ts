import { parse } from 'smol-toml';
import type { Position } from '../net';
import { mapOf } from './map';

const story = import.meta.glob<string>('../../../content/story/story.toml', {
  eager: true,
  query: '?raw',
  import: 'default',
});

/** Somewhere the player can find a fact about Aris's attack, on a cell of a map. */
export type Clue = { id: string; label: string; map: string; x: number; y: number };

export function cluesOf(toml: string): Clue[] {
  const { clues } = parse(toml) as { clues?: Clue[] };
  return (clues ?? []).map(({ id, label, map, x, y }) => ({ id, label, map, x, y }));
}

/** The clues in content/story/story.toml. */
export const clues: readonly Clue[] = Object.values(story).flatMap(cluesOf);

/** Inside the server's `clue_reach` of a tile and a half, as for a pile. */
export const CLUE_TILES = 1;

/** The nearest clue on this map within reach of where the player stands. */
export function clueInReach(position: Position, from: readonly Clue[]): { clue: Clue; tiles: number } | undefined {
  let best: { clue: Clue; tiles: number } | undefined;
  for (const clue of from) {
    if (clue.map !== mapOf(position)) continue;
    const tiles = Math.hypot(clue.x - position.x, clue.y - position.y);
    if (tiles <= CLUE_TILES && (!best || tiles < best.tiles)) best = { clue, tiles };
  }
  return best;
}
