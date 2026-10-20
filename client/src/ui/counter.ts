import type { Interactable } from '../world/interactables';
import { mapOf } from '../world/map';
import { NEWS_KEY } from './tuning';
import type { WorldView } from './world-view';

/** How far past the counter's far end whoever serves at it can stand. */
const PAST_END_TILES = 2;
const HINT_MS = 2500;

/** Whoever's on the counter's row and side of the stand, past the customers' pickup beside it, nearest it. */
export function servingAt(counter: Interactable, view: WorldView): string | undefined {
  const [stand] = counter.stand;
  if (!stand) return undefined;
  const { area } = counter;
  const way = area.x + area.width / 2 < stand.x + 0.5 ? -1 : 1;
  const farEnd = way < 0 ? area.x : area.x + area.width - 1;
  const reach = (farEnd - stand.x) * way + PAST_END_TILES;
  let best: [number, string] | undefined;
  for (const id of view.npcIds()) {
    const at = view.positionOf(id);
    if (!at || mapOf(at) !== counter.map || Math.abs(at.y - stand.y) >= 1) continue;
    const along = (at.x - stand.x) * way;
    if (along <= 1 || along > reach) continue;
    if (!best || along < best[0]) best = [along, id];
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
