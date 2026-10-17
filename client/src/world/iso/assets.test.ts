import { describe, expect, it } from 'vitest';
import { characterLights, imageUrl, manifestUrl } from './assets';
import { sceneryImages, type SceneryManifest } from './manifest';
import { LIGHTING_SETS, type LightingSet } from './time-of-day';

const manifests = import.meta.glob<SceneryManifest>('../../../../content/art/iso/scenery/*.json', {
  eager: true,
  import: 'default',
});

describe('iso assets', () => {
  it('has a manifest for every lighting set', () => {
    for (const set of Object.keys(LIGHTING_SETS) as LightingSet[]) expect(manifestUrl(set)).toBeTruthy();
  });

  it('has every image each manifest names, and its light map', () => {
    for (const manifest of Object.values(manifests)) {
      expect(manifest.format).toBe(1);
      for (const image of sceneryImages(manifest)) expect(imageUrl(image), image).toBeTruthy();
      expect(imageUrl(manifest.light_map.image)).toBeTruthy();
    }
  });

  it('pairs every object across the sets by id', () => {
    const ids = Object.values(manifests).map(({ objects }) => objects.map(({ id }) => id));
    for (const set of ids) expect(set).toEqual(ids[0]);
  });

  it("has every lighting set's constants for characters", () => {
    expect(Object.keys(characterLights).sort()).toEqual(Object.keys(LIGHTING_SETS).sort());
  });
});
