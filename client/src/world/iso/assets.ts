import type { SetLight } from './lighting';
import type { CharacterManifest } from './sheets';
import type { LightingSet } from './time-of-day';

const SCENERY = '../../../../content/art/iso/scenery/';
const CHARACTERS = '../../../../content/art/iso/characters/';

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
const characters = import.meta.glob<CharacterManifest>(
  '../../../../content/art/iso/characters/characters.json',
  { eager: true, import: 'default' },
);
const sheets = import.meta.glob<string>('../../../../content/art/iso/characters/*.webp', {
  eager: true,
  query: '?no-inline',
  import: 'default',
});

export const manifestUrl = (set: LightingSet): string | undefined => manifests[`${SCENERY}${set}.json`];

/** A manifest names its images relative to its own folder. */
export const imageUrl = (image: string): string | undefined => images[SCENERY + image];

export const characterManifest: CharacterManifest = characters[`${CHARACTERS}characters.json`];

/** Each lighting set's tint and drop shadow for characters, whatever art draws them. */
export const characterLights: Record<LightingSet, SetLight> = characterManifest.sets;

export const sheetUrl = (image: string): string | undefined => sheets[CHARACTERS + image];

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
