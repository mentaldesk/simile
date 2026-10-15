import { describe, expect, it } from 'vitest';
import { characterKeys, characters } from './assets';
import { characterFor, poseOf, walkFrames } from './sprites';

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

  it('gives the fixture NPCs different samples', () => {
    const fixtures = ['mei', 'viktor', 'suki'].map((id) => characterFor(id, characterKeys));
    expect(new Set(fixtures).size).toBe(3);
  });
});

describe('the character atlases', () => {
  it('include the player and the samples, each with a walk cycle in every direction', () => {
    expect(characterKeys).toContain('player');
    expect(characterKeys.filter((key) => key.startsWith('sample_')).length).toBeGreaterThan(0);
    for (const { atlas } of characters) {
      const frames = Object.keys((atlas as { frames: object }).frames);
      for (const facing of ['down', 'left', 'right', 'up'] as const) {
        for (const frame of walkFrames(facing)) expect(frames).toContain(frame);
      }
    }
  });
});

describe('poseOf', () => {
  it('plays the walk for the facing while walking', () => {
    expect(poseOf('mei', { position: { x: 0, y: 0 }, facing: 'left', walking: true })).toEqual({
      animation: 'mei-walk-left',
    });
  });

  it('stands on the middle column when still', () => {
    expect(poseOf('mei', { position: { x: 0, y: 0 }, facing: 'up', walking: false })).toEqual({
      frame: 'up-1',
    });
  });

  it('walks step, stand, step, stand', () => {
    expect(walkFrames('down')).toEqual(['down-0', 'down-1', 'down-2', 'down-1']);
  });
});
