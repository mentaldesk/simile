import type { CharacterLights, SetLight } from './lighting';
import type { LightingSet } from './time-of-day';

const SCENERY = '../../../../content/art/iso/scenery/';
const INTERIORS = '../../../../content/art/iso/interiors/';

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
const interiorManifests = import.meta.glob<string>('../../../../content/art/iso/interiors/*.json', {
  eager: true,
  query: '?url',
  import: 'default',
});
const interiorImages = import.meta.glob<string>('../../../../content/art/iso/interiors/*/*.webp', {
  eager: true,
  query: '?no-inline',
  import: 'default',
});
const lights = import.meta.glob<CharacterLights>('../../../../content/art/iso/characters/lights.json', {
  eager: true,
  import: 'default',
});

export const manifestUrl = (set: LightingSet): string | undefined => manifests[`${SCENERY}${set}.json`];

/** A manifest names its images relative to its own folder. */
export const imageUrl = (image: string): string | undefined => images[SCENERY + image];

export const interiorManifestUrl = (map: string): string | undefined =>
  interiorManifests[`${INTERIORS}${map}.json`];

export const interiorImageUrl = (image: string): string | undefined => interiorImages[INTERIORS + image];

/** Each lighting set's tint and drop shadow for characters, whatever art draws them. */
export const characterLights: Record<LightingSet, SetLight> = Object.values(lights)[0].sets;

export const figureMetres: number = Object.values(lights)[0].figure_m;

export async function loadImage(url: string): Promise<HTMLImageElement> {
  const image = new Image();
  image.src = url;
  await image.decode();
  return image;
}

/** Decoded off the main thread, and premultiplied as Phaser's WebGL textures expect. */
export async function loadBitmap(url: string): Promise<ImageBitmap> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url}: ${response.status}`);
  return createImageBitmap(await response.blob(), { premultiplyAlpha: 'premultiply' });
}

export async function imagePixels(url: string): Promise<Uint8ClampedArray> {
  const image = await loadImage(url);
  const canvas = document.createElement('canvas');
  [canvas.width, canvas.height] = [image.width, image.height];
  const context = canvas.getContext('2d', { willReadFrequently: true })!;
  context.drawImage(image, 0, 0);
  return context.getImageData(0, 0, image.width, image.height).data;
}
