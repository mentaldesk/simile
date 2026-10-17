import { describe, expect, it } from 'vitest';
import { characterKeys } from './assets';
import { characterFor } from './sprites';

const GENERATED_NPCS = import.meta.glob('../../../content/npcs/*.json');
const AVAILABLE = ['player', 'mei', 'sample_artist', 'sample_barista', 'sample_coder'];

describe('characterFor', () => {
  it('uses the entity’s own atlas when there is one', () => {
    expect(characterFor('mei', AVAILABLE)).toBe('mei');
    expect(characterFor('player', AVAILABLE)).toBe('player');
  });

  it('falls back to the same sample every time', () => {
    const sample = characterFor('viktor', AVAILABLE);
    expect(sample).toMatch(/^sample_/);
    expect(characterFor('viktor', [...AVAILABLE].reverse())).toBe(sample);
  });

  it('spreads NPCs over the samples', () => {
    const ids = Array.from({ length: 30 }, (_, i) => `npc_${i}`);
    expect(new Set(ids.map((id) => characterFor(id, AVAILABLE))).size).toBe(3);
  });

  it('draws every generated NPC with its own atlas', () => {
    const npcs = Object.keys(GENERATED_NPCS).map((path) => path.slice(path.lastIndexOf('/') + 1, -5));
    expect(npcs.length).toBeGreaterThan(0);
    for (const id of npcs) expect(characterFor(id, characterKeys)).toBe(id);
  });

  it('gives the fixture NPCs different samples', () => {
    const fixtures = ['mei', 'viktor', 'suki'].map((id) => characterFor(id, characterKeys));
    expect(new Set(fixtures).size).toBe(3);
  });
});

describe('the character atlases', () => {
  it('include the player and the samples', () => {
    expect(characterKeys).toContain('player');
    expect(characterKeys.filter((key) => key.startsWith('sample_')).length).toBeGreaterThan(0);
  });
});
