import type { DollManifest } from './manifest';

const manifests = import.meta.glob<DollManifest>('../../../content/dolls/*.json', {
  eager: true,
  import: 'default',
});
const atlases = import.meta.glob<string>('../../../content/dolls/*.webp', {
  eager: true,
  query: '?url',
  import: 'default',
});

const folder = (path: string) => path.slice(0, path.lastIndexOf('/') + 1);
const stem = (path: string) => path.slice(path.lastIndexOf('/') + 1, path.lastIndexOf('.'));

/** The residents' and the player's dolls in `content/dolls/`, by id, with their atlases' URLs. */
export const dolls: Record<string, DollManifest> = Object.fromEntries(
  Object.entries(manifests).map(([path, doll]) => {
    const url = (name?: string) => (name ? atlases[folder(path) + name] : undefined);
    return [
      doll.id ?? stem(path),
      { ...doll, flat: url(doll.flat) ?? '', painted: url(doll.painted) },
    ];
  }),
);

/** A flat doll for any look, at once, from the server. The creator previews with it. */
export async function flatDoll(
  appearance: object,
  character?: string,
  fetcher: typeof fetch = fetch,
): Promise<DollManifest> {
  const response = await fetcher('/api/dolls/flat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ appearance, character }),
  });
  if (!response.ok) throw new Error(`No flat doll: ${response.status}`);
  return (await response.json()) as DollManifest;
}

/** A doll a job published, its atlases' URLs resolved against its manifest's. */
export async function loadDoll(url: string, fetcher: typeof fetch = fetch): Promise<DollManifest> {
  const response = await fetcher(url);
  if (!response.ok) throw new Error(`No doll at ${url}: ${response.status}`);
  const doll = (await response.json()) as DollManifest;
  const base = new URL(url, globalThis.location?.href);
  const resolve = (name?: string) => (name ? new URL(name, base).href : undefined);
  return {
    ...doll,
    flat: resolve(doll.flat) ?? '',
    painted: resolve(doll.painted),
  };
}
