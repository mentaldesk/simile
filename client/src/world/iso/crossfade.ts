import { blend, setsWithin, type Layer, type LightingSet } from './time-of-day';

/** Lifts the incoming image of a pair above the outgoing, and stays below `RESIDENT_TIE`. */
export const PAIR_DEPTH = 1e-4;

export const PRELOAD_SECONDS = 120;

/** Bounds how many sets a fast clock keeps in memory. */
export const MAX_LOOKAHEAD_HOURS = 3;

/** How long a frame spends adding a loaded set to the scene, after its first task. */
export const UPLOAD_MS_PER_FRAME = 4;

/** The outgoing image goes in the last 1 / this of the weight, so soft edges end the fade single. */
const OUTGOING_FADE = 20;

/** Outgoing under incoming at its weight, faded together to `alpha` as one image would be. */
export function layerAlphas<L extends { weight: number }>(layers: readonly L[], alpha = 1): number[] {
  if (layers.length < 2) return layers.map(() => alpha);
  const weight = layers[1].weight;
  const incoming = alpha * weight;
  const covering = incoming === 1 ? 0 : (alpha - incoming) / (1 - incoming);
  return [Math.min(covering, OUTGOING_FADE * (1 - weight)), incoming];
}

type State = 'loading' | 'ready' | 'failed';

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
    const ahead = Math.min((speed * PRELOAD_SECONDS) / 3600, MAX_LOOKAHEAD_HOURS);
    const wanted = setsWithin(hour, ahead);
    for (const set of wanted) if (!this.states.has(set)) this.start(set);
    this.layers = this.drawable(blend(hour));
    const drawn = new Set(this.layers.map(({ set }) => set));
    for (const [set, state] of this.states) {
      if (state !== 'ready' || wanted.has(set) || drawn.has(set)) continue;
      this.states.delete(set);
      this.unload(set);
    }
    return this.layers;
  }

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

export class Uploads {
  private readonly queue: { run: () => void; done?: () => void }[] = [];

  add(tasks: (() => void)[]): Promise<void> {
    if (tasks.length === 0) return Promise.resolve();
    return new Promise((resolve) => {
      const last = tasks.length - 1;
      tasks.forEach((run, i) => this.queue.push({ run, done: i === last ? resolve : undefined }));
    });
  }

  /** Runs one task, then more until `budgetMs` has passed. */
  run(budgetMs: number, now: () => number = () => performance.now()): void {
    const start = now();
    do {
      const task = this.queue.shift();
      if (!task) return;
      task.run();
      task.done?.();
    } while (now() - start < budgetMs);
  }
}
