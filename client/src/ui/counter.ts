import type { Interactable } from '../world/interactables';
import { mapOf } from '../world/map';
import { NEWS_KEY } from './tuning';
import type { WorldView } from './world-view';

/** How many rows behind a counter, and tiles along it, whoever serves at it stands. */
const BEHIND_ROWS = 3;
const ALONG_TILES = 4;
const HINT_MS = 2500;

/** The NPC serving at a counter: behind it, nearest the tile the player orders from. */
export function servingAt(counter: Interactable, view: WorldView): string | undefined {
  const [stand] = counter.stand;
  if (!stand) return undefined;
  let best: [number, string] | undefined;
  for (const id of view.npcIds()) {
    const at = view.positionOf(id);
    if (!at || mapOf(at) !== counter.map) continue;
    const behind = stand.y - at.y;
    if (behind < 0.5 || behind > BEHIND_ROWS || Math.abs(at.x - stand.x) > ALONG_TILES) continue;
    const distance = Math.hypot(at.x - stand.x, behind);
    if (!best || distance < best[0]) best = [distance, id];
  }
  return best?.[1];
}

/** "Press E to order at the counter." while the player stands at a counter. */
export class CounterPrompt {
  private readonly hint: HTMLElement;
  private flashing?: ReturnType<typeof setTimeout>;

  constructor(parent: HTMLElement) {
    this.hint = parent.appendChild(document.createElement('div'));
    this.hint.className = 'counter-hint';
    this.hint.hidden = true;
  }

  update(counter: Interactable | undefined, shown: boolean): void {
    if (this.flashing) return;
    this.hint.hidden = !counter || !shown;
    if (counter) {
      const prompt = counter.prompt.charAt(0).toLowerCase() + counter.prompt.slice(1);
      this.hint.textContent = `Press ${NEWS_KEY.toUpperCase()} to ${prompt}.`;
    }
  }

  flash(message: string): void {
    this.hint.textContent = message;
    this.hint.hidden = false;
    clearTimeout(this.flashing);
    this.flashing = setTimeout(() => (this.flashing = undefined), HINT_MS);
  }
}

/** The counter the player is standing at, if the interactable they're at is one. */
export function counterOf(interactable: Interactable | undefined): Interactable | undefined {
  return interactable?.kind === 'counter' ? interactable : undefined;
}
