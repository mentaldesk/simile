import type { Position } from '../../net';
import type { Door } from '../doors';
import { mapOf, VILLAGE } from '../map';

/** How long an interior stays loaded once the player is out of it and away from its door. */
export const INTERIOR_KEEP_SECONDS = 30;

/** How near its door, in tiles, the player starts loading an interior. */
export const INTERIOR_NEAR_TILES = 6;

/** How long after an interior fails to load it's tried again, doubling with each failure. */
export const INTERIOR_RETRY_SECONDS = 5;

export const INTERIOR_RETRY_MAX_SECONDS = 300;

/** The interior the player is in, and those whose doors they're near. */
export function interiorsWanted(position: Position, doors: readonly Door[]): string[] {
  const near = doors
    .filter(({ x, y }) => Math.hypot(x - position.x, y - position.y) <= INTERIOR_NEAR_TILES)
    .map(({ to }) => to.map);
  return [mapOf(position), ...near].filter((map) => map !== VILLAGE);
}

type Entry<S> = { state: 'loading'; stale: boolean } | { state: 'ready'; scenery: S } | { state: 'failed'; retry: number };

/** Loads interiors as they're wanted, and unloads each `keepSeconds` after it last was. */
export class InteriorLoader<S> {
  private readonly entries = new Map<string, Entry<S>>();
  private readonly wantedAt = new Map<string, number>();
  private readonly failures = new Map<string, number>();
  private readonly load: (map: string) => Promise<S>;
  private readonly unload: (map: string, scenery: S) => void;
  private readonly keepSeconds: number;
  private now = 0;

  constructor(
    load: (map: string) => Promise<S>,
    unload: (map: string, scenery: S) => void,
    keepSeconds = INTERIOR_KEEP_SECONDS,
  ) {
    this.load = load;
    this.unload = unload;
    this.keepSeconds = keepSeconds;
  }

  /** `now` is in seconds. */
  update(wanted: Iterable<string>, now: number): void {
    this.now = now;
    for (const map of wanted) this.want(map);
    for (const [map, entry] of this.entries) {
      if (entry.state !== 'ready' || now - this.wantedAt.get(map)! < this.keepSeconds) continue;
      this.entries.delete(map);
      this.unload(map, entry.scenery);
    }
  }

  /** The interior once it's loaded, starting to load it if it's due. */
  get(map: string): S | undefined {
    this.want(map);
    const entry = this.entries.get(map);
    return entry?.state === 'ready' ? entry.scenery : undefined;
  }

  *loaded(): Iterable<S> {
    for (const entry of this.entries.values()) if (entry.state === 'ready') yield entry.scenery;
  }

  /** Unloads every interior to load again, as a restored WebGL context needs. */
  reset(): void {
    for (const [map, entry] of this.entries) {
      if (entry.state === 'loading') entry.stale = true;
      else {
        this.entries.delete(map);
        if (entry.state === 'ready') this.unload(map, entry.scenery);
      }
    }
  }

  private want(map: string): void {
    this.wantedAt.set(map, this.now);
    const entry = this.entries.get(map);
    if (!entry || (entry.state === 'failed' && this.now >= entry.retry)) this.start(map);
  }

  private start(map: string): void {
    const loading: Entry<S> = { state: 'loading', stale: false };
    this.entries.set(map, loading);
    this.load(map).then(
      (scenery) => {
        this.failures.delete(map);
        if (!loading.stale) {
          this.entries.set(map, { state: 'ready', scenery });
          return;
        }
        this.entries.delete(map);
        this.unload(map, scenery);
      },
      (error: unknown) => {
        console.error(`Couldn't load the ${map} interior`, error);
        const failures = (this.failures.get(map) ?? 0) + 1;
        this.failures.set(map, failures);
        const wait = Math.min(INTERIOR_RETRY_SECONDS * 2 ** (failures - 1), INTERIOR_RETRY_MAX_SECONDS);
        this.entries.set(map, { state: 'failed', retry: this.now + wait });
      },
    );
  }
}
