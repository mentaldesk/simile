import type { LightingSet } from './time-of-day';

const SCENERY = '../../../../content/art/iso/scenery/';

const manifests = import.meta.glob<string>('../../../../content/art/iso/scenery/*.json', {
  eager: true,
  query: '?url',
  import: 'default',
});
const images = import.meta.glob<string>('../../../../content/art/iso/scenery/*/*.webp', {
  eager: true,
  query: '?no-inline',
  import: 'default',
});

export const manifestUrl = (set: LightingSet): string | undefined => manifests[`${SCENERY}${set}.json`];

/** A manifest names its images relative to its own folder. */
export const imageUrl = (image: string): string | undefined => images[SCENERY + image];
