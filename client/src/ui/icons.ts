import manifest from '../../../content/icons/icons.json';

const files = import.meta.glob<string>(['../../../content/icons/*.webp', '!../../../content/icons/preview.webp'], {
  eager: true,
  query: '?url',
  import: 'default',
});

const listed: Record<string, { file: string }> = manifest.icons;

/** An icon's URL from `content/icons/`, by its id in the catalogue, or undefined if it isn't painted. */
export function iconUrl(id: string): string | undefined {
  const entry = listed[id];
  return entry && files[`../../../content/icons/${entry.file}`];
}
