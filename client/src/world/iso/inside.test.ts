import { describe, expect, it } from 'vitest';
import { cutawaysOf, framesOn, INSIDE, INSIDE_SUN, insideLight, sunShadow } from './inside';
import type { CharacterLights } from './lighting';
import type { SceneryManifest } from './manifest';

const glob = <T>(found: Record<string, T>) => Object.values(found);
const interiors = glob(
  import.meta.glob<SceneryManifest>('../../../../content/art/iso/interiors/*.json', {
    eager: true,
    import: 'default',
  }),
);
const [village] = glob(
  import.meta.glob<SceneryManifest>('../../../../content/art/iso/scenery/afternoon.json', {
    eager: true,
    import: 'default',
  }),
);
const [lights] = glob(
  import.meta.glob<CharacterLights>('../../../../content/art/iso/characters/lights.json', {
    eager: true,
    import: 'default',
  }),
);
const { tile } = village;
const figureTiles = lights.figure_m / tile.metres;

describe('sunShadow', () => {
  it.each(Object.entries(lights.sets))('works out the %s shadow as lights.json has it', (_, set) => {
    const { direction, length, tip } = sunShadow(set.sun, figureTiles, tile);
    expect(direction[0]).toBeCloseTo(set.shadow.direction[0], 3);
    expect(direction[1]).toBeCloseTo(set.shadow.direction[1], 3);
    expect(length).toBeCloseTo(set.shadow.length, 2);
    expect(tip[0]).toBeCloseTo(set.shadow.tip[0], 0);
    expect(tip[1]).toBeCloseTo(set.shadow.tip[1], 0);
  });
});

describe('insideLight', () => {
  it('is for the light every interior was rendered in', () => {
    expect(interiors).toHaveLength(4);
    for (const manifest of interiors) {
      expect(manifest.set).toBe(INSIDE);
      expect(manifest.sun).toEqual(INSIDE_SUN);
      expect(manifest.tile).toEqual(tile);
    }
  });

  it('casts a short soft shadow away from the high key light, to the north', () => {
    const { shadow, tint } = insideLight(INSIDE_SUN, figureTiles, tile);
    expect(shadow.length).toBeLessThan(1);
    expect(shadow.direction[1]).toBeLessThan(-0.9);
    for (const set of Object.values(lights.sets)) expect(shadow.strength).toBeLessThan(set.shadow.strength);
    expect(new Set(tint).size).toBe(1);
  });
});

describe('cutawaysOf', () => {
  it('cuts away the village’s buildings', () => {
    const cut = cutawaysOf(village.objects);
    expect(cut.length).toBeGreaterThan(0);
    expect(cut).toEqual(village.objects.filter(({ kind }) => kind === 'building'));
  });

  it('cuts away the gallery’s free-standing walls, and not the walls around a room', () => {
    const ids = (map: string) =>
      cutawaysOf(interiors.find((manifest) => manifest.map.id === map)!.objects).map(({ id }) => id);
    expect(ids('gallery').length).toBeGreaterThan(0);
    for (const id of ids('gallery')) expect(id).toMatch(/^partition-/);
    expect(ids('coffee_shop')).toEqual([]);
  });

  it('fades the frames on a partition with it', () => {
    const { objects } = interiors.find((manifest) => manifest.map.id === 'gallery')!;
    const frames = (wall: string) =>
      framesOn(objects.find(({ id }) => id === wall)!, objects).map(({ id }) => id);
    expect(frames('partition-4-9')).toEqual(['painting_8', 'painting_9', 'painting_10']);
    expect(frames('partition-18-9')).toEqual(['painting_11', 'painting_12', 'painting_13']);
  });
});
