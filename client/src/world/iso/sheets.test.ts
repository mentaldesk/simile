import { describe, expect, it } from 'vitest';
import { WALKING_SPEED } from '../tuning';
import type { SceneryManifest } from './manifest';
import { directionFor, sheetFor, sheetFrame, walkTimeScale, type CharacterManifest } from './sheets';
import { LIGHTING_SETS } from './time-of-day';

const manifest = Object.values(
  import.meta.glob<CharacterManifest>('../../../../content/art/iso/characters/characters.json', {
    eager: true,
    import: 'default',
  }),
)[0];
const { tile } = Object.values(
  import.meta.glob<SceneryManifest>('../../../../content/art/iso/scenery/*.json', {
    eager: true,
    import: 'default',
  }),
)[0];
const { directions } = manifest;

describe('the character manifest', () => {
  it('gives the scene its frame, feet and figure height', () => {
    expect(manifest.format).toBe(1);
    expect(sheetFrame(manifest, tile)).toEqual({
      width: 72,
      height: 129,
      anchor: { x: 36, y: 110 },
      figureHeight: 96,
    });
  });

  it('has constants for every lighting set', () => {
    expect(Object.keys(manifest.sets).sort()).toEqual(Object.keys(LIGHTING_SETS).sort());
  });

  it('has a walk and an idle for every direction', () => {
    for (const { name } of directions) {
      expect(manifest.animations.walk.frames[name]).toHaveLength(8);
      expect(manifest.animations.idle.frames[name]).toHaveLength(4);
    }
  });
});

describe('directionFor', () => {
  it('faces the way of a step on the map', () => {
    expect(directionFor({ x: 0, y: 1 }, directions, 'n')).toBe('s');
    expect(directionFor({ x: 2, y: 2 }, directions, 'n')).toBe('se');
    expect(directionFor({ x: -0.1, y: -0.1 }, directions, 's')).toBe('nw');
    expect(directionFor({ x: 1, y: 0 }, directions, 'n')).toBe('e');
    expect(directionFor({ x: -1, y: 1 }, directions, 'n')).toBe('sw');
  });

  it('compares angles, so the longer diagonal vectors win no more than their share', () => {
    expect(directionFor({ x: 1, y: 0.35 }, directions, 'n')).toBe('e');
    expect(directionFor({ x: 1, y: 0.45 }, directions, 'n')).toBe('se');
    expect(directionFor({ x: -0.35, y: -1 }, directions, 's')).toBe('n');
  });

  it('keeps facing the same way standing still', () => {
    expect(directionFor({ x: 0, y: 0 }, directions, 'ne')).toBe('ne');
  });
});

describe('walkTimeScale', () => {
  const { walk } = manifest.animations;

  it('plays the walk at about its fps at walking speed', () => {
    expect(walkTimeScale(WALKING_SPEED, walk)).toBeCloseTo(1, 1);
  });

  it('covers tiles_per_cycle with each cycle, at any speed', () => {
    for (const speed of [0.5, WALKING_SPEED, 2 * WALKING_SPEED]) {
      const cycleSeconds = 8 / (walk.fps * walkTimeScale(speed, walk));
      expect(cycleSeconds * speed).toBeCloseTo(walk.tiles_per_cycle);
    }
  });
});

describe('sheetFor', () => {
  const sheets = Object.keys(manifest.characters);

  it('draws everyone with a sheet in their own', () => {
    expect(sheetFor('player', sheets, 'player')).toBe('player');
    expect(sheetFor('henrietta', sheets, 'player')).toBe('henrietta');
  });

  it('gives anyone else a resident, the same one each time', () => {
    const sheet = sheetFor('newcomer', sheets, 'player');
    expect(sheets).toContain(sheet);
    expect(sheet).not.toBe('player');
    expect(sheetFor('newcomer', sheets, 'player')).toBe(sheet);
    expect(sheetFor('anyone', ['player'], 'player')).toBe('player');
  });
});
