import { npcAt } from '../world/hit';
import type { Dialogue } from './dialogue';
import { CHAT_RANGE_TILES } from './tuning';
import { distanceFromPlayer, type ScreenPoint, type WorldView } from './world-view';

export type Talks = Pick<Dialogue, 'partner' | 'busy'>;

export type Refusal = 'busy' | 'far';

const claims = new Set<() => boolean>();

/** While `claimed()` is true, clicks on NPCs are the caller's and don't choose who to talk to. */
export function claimClicks(claimed: () => boolean): () => void {
  claims.add(claimed);
  return () => claims.delete(claimed);
}

/** The NPC a click at `point` picks, unless something claimed the click. */
export function clicked(point: ScreenPoint, view: WorldView): string | undefined {
  return [...claims].some((claimed) => claimed()) ? undefined : npcAt(point, view);
}

/** Who the chat box talks to: whom the player chose, else their partner, else the nearest. */
export class ChatTarget {
  private chosen?: string;
  private held?: string;
  private readonly view: () => WorldView;
  private readonly talks: Talks;

  constructor(view: () => WorldView, talks: Talks) {
    this.view = view;
    this.talks = talks;
  }

  current(): string | undefined {
    if (this.held !== undefined) return this.held;
    if (this.chosen !== undefined && this.refusal(this.chosen)) this.chosen = undefined;
    return this.chosen ?? this.talks.partner() ?? this.reachable()[0];
  }

  /** Who the player can talk to now, nearest first. */
  reachable(): string[] {
    const view = this.view();
    const reachable: [number, string][] = [];
    for (const id of view.npcIds()) {
      if (!this.refusal(id)) reachable.push([distanceFromPlayer(view, id) ?? Infinity, id]);
    }
    return reachable.sort(([a], [b]) => a - b).map(([, id]) => id);
  }

  refusal(npcId: string): Refusal | undefined {
    if (npcId === this.talks.partner()) return undefined;
    if (this.talks.busy(npcId)) return 'busy';
    const distance = distanceFromPlayer(this.view(), npcId);
    return distance === undefined || distance > CHAT_RANGE_TILES ? 'far' : undefined;
  }

  choose(npcId: string): void {
    this.chosen = npcId;
    if (this.held !== undefined) this.held = npcId;
  }

  cycle(step: 1 | -1): string | undefined {
    const reachable = this.reachable();
    if (reachable.length === 0) return undefined;
    const at = reachable.indexOf(this.current() ?? '');
    const next = at === -1 ? (step === 1 ? 0 : -1) : at + step;
    const npcId = reachable[(next + reachable.length) % reachable.length];
    this.choose(npcId);
    return npcId;
  }

  clear(): void {
    this.chosen = this.held = undefined;
  }

  /** Keeps the target as it is, wherever they go, until `release`: the chat box is open to them. */
  hold(): string | undefined {
    return (this.held = this.current());
  }

  release(): void {
    this.held = undefined;
  }
}
