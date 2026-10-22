import { describe, expect, it } from 'vitest';
import { clueInReach, clues, cluesOf } from './clues';
import { usedByE } from './reach';

const at = (map: string, x: number, y = 2) => ({ x, y, map });

describe('clues', () => {
  it('are the story’s, on cells of Aris’s workshop', () => {
    expect(clues).toEqual([
      { id: 'aris_notes', label: "Aris's notes", map: 'maker_space_floor_0', x: 3, y: 2 },
      { id: 'door_frame', label: 'The splintered door frame', map: 'maker_space_floor_0', x: 13, y: 2 },
    ]);
    expect(cluesOf('[aris]\nname = "Aris"\n')).toEqual([]);
  });

  it('are in reach within a tile on their map, nearest first', () => {
    expect(clueInReach(at('maker_space_floor_0', 3.6), clues)).toMatchObject({ clue: { id: 'aris_notes' } });
    expect(clueInReach(at('maker_space_floor_0', 12.2), clues)?.tiles).toBeCloseTo(0.8);
    expect(clueInReach(at('maker_space_floor_0', 8), clues)).toBeUndefined();
    expect(clueInReach(at('maker_space_floor_1', 3), clues)).toBeUndefined();
  });

  it('are what E uses, rather than the workshop’s door beside the door frame', () => {
    expect(usedByE(at('maker_space_floor_0', 3))).toMatchObject({ kind: 'clue', tiles: 0, clue: { id: 'aris_notes' } });
    expect(usedByE(at('maker_space_floor_0', 13.5))).toMatchObject({ kind: 'clue', clue: { id: 'door_frame' } });
  });
});
