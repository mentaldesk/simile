import { blend, type Layer, type LightingSet } from './time-of-day';

/** Lifts the incoming image of a pair above the outgoing, and stays below `RESIDENT_TIE`. */
export const PAIR_DEPTH = 1e-4;

/** Real seconds ahead to load the next set, so it's ready when its fade starts. */
export const PRELOAD_SECONDS = 120;

/** The outgoing image goes in the last 1 / this of the weight, so soft edges end the fade single. */
const OUTGOING_FADE = 20;

/** Outgoing under incoming at its weight, faded together to `alpha` as one image would be. */
export function layerAlphas(layers: readonly Layer[], alpha = 1): number[] {
  if (layers.length < 2) return layers.map(() => alpha);
  const weight = layers[1].weight;
  const incoming = alpha * weight;
  const covering = incoming === 1 ? 0 : (alpha - incoming) / (1 - incoming);
  return [Math.min(covering, OUTGOING_FADE * (1 - weight)), incoming];
}

type State = 'loading' | 'ready' | 'failed';

/** Keeps in memory only the sets the sim clock needs now and in the next `PRELOAD_SECONDS`. */
export class SetLoader {
  layers: Layer[] = [];
  private readonly states = new Map<LightingSet, State>();
  private readonly load: (set: LightingSet) => Promise<void>;
  private readonly unload: (set: LightingSet) => void;

  constructor(load: (set: LightingSet) => Promise<void>, unload: (set: LightingSet) => void) {
    this.load = load;
    this.unload = unload;
  }

  update(hour: number, speed: number): Layer[] {
    const now = blend(hour);
    const soon = blend(hour + (speed * PRELOAD_SECONDS) / 3600);
    const wanted = new Set([...now, ...soon].map(({ set }) => set));
    for (const set of wanted) if (!this.states.has(set)) this.start(set);
    this.layers = this.drawable(now);
    const drawn = new Set(this.layers.map(({ set }) => set));
    for (const [set, state] of this.states) {
      if (state !== 'ready' || wanted.has(set) || drawn.has(set)) continue;
      this.states.delete(set);
      this.unload(set);
    }
    return this.layers;
  }

  /** What was drawn until every set in `layers` has loaded, leaving out any that failed. */
  private drawable(layers: Layer[]): Layer[] {
    if (layers.some(({ set }) => this.states.get(set) === 'loading')) return this.layers;
    const ready = layers.filter(({ set }) => this.states.get(set) === 'ready');
    if (ready.length === layers.length) return layers;
    const total = ready.reduce((sum, { weight }) => sum + weight, 0);
    return total > 0 ? ready.map(({ set, weight }) => ({ set, weight: weight / total })) : this.layers;
  }

  private start(set: LightingSet): void {
    this.states.set(set, 'loading');
    this.load(set).then(
      () => this.states.set(set, 'ready'),
      (error: unknown) => {
        console.error(`Couldn't load the ${set} lighting set`, error);
        this.states.set(set, 'failed');
      },
    );
  }
}
