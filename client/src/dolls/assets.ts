import { isFigure, type DollManifest, type FigureManifest, type FlatDoll } from './manifest';

const manifests = import.meta.glob<FigureManifest>('../../../content/dolls/*.json', {
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

/** The residents', the doctor's and the player's figures in `content/dolls/`, by id, with their atlases' URLs. */
export const dolls: Record<string, FigureManifest> = Object.fromEntries(
  Object.entries(manifests).map(([path, figure]) => [
    figure.id ?? stem(path),
    { ...figure, painted: figure.painted && atlases[folder(path) + figure.painted] },
  ]),
);

/** A flat doll for any look, at once, from the server. The creator previews with it. */
export async function flatDoll(
  appearance: object,
  character?: string,
  fetcher: typeof fetch = fetch,
): Promise<FlatDoll> {
  const response = await fetcher('/api/dolls/flat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ appearance, character }),
  });
  if (!response.ok) throw new Error(`No flat doll: ${response.status}`);
  return (await response.json()) as FlatDoll;
}

/** A figure a job painted, its atlas's URL resolved against its manifest's. A paper doll painted
 * before figures is refused, so the creator paints the look again. */
export async function loadDoll(url: string, fetcher: typeof fetch = fetch): Promise<DollManifest> {
  const response = await fetcher(url);
  if (!response.ok) throw new Error(`No doll at ${url}: ${response.status}`);
  const doll = (await response.json()) as DollManifest;
  if (!isFigure(doll)) throw new Error(`${url} is a paper doll, painted before figures`);
  const base = new URL(url, globalThis.location?.href);
  const resolve = (name?: string) => (name ? new URL(name, base).href : undefined);
  return { ...doll, painted: resolve(doll.painted) };
}
