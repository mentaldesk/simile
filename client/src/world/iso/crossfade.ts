import { blend, nextSet, type Layer, type LightingSet } from './time-of-day';

/** Lifts the incoming image of a pair above the outgoing, and stays below `RESIDENT_TIE`. */
export const PAIR_DEPTH = 1e-4;

export const PRELOAD_SECONDS = 120;

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

/** Loads the sets the clock draws, and the next one before its fade if that keeps it to two. */
export class SetLoader {
  layers: Layer[] = [];
  private readonly states = new Map<LightingSet, State>();
  /** Loading when `reset` was called, so unloaded once they finish. */
  private readonly stale = new Set<LightingSet>();
  private readonly load: (set: LightingSet) => Promise<void>;
  private readonly unload: (set: LightingSet) => void;

  constructor(load: (set: LightingSet) => Promise<void>, unload: (set: LightingSet) => void) {
    this.load = load;
    this.unload = unload;
  }

  update(hour: number, speed: number): Layer[] {
    const now = blend(hour);
    const wanted = new Set(now.map(({ set }) => set));
    const next = nextSet(hour, (speed * PRELOAD_SECONDS) / 3600);
    const held = new Set([...wanted, ...this.layers.map(({ set }) => set)]);
    if (next && held.size < 2) wanted.add(next);
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

  /** Unloads every set to load again, as a restored WebGL context needs. */
  reset(): void {
    this.layers = [];
    for (const [set, state] of this.states) {
      if (state === 'loading') {
        this.stale.add(set);
        continue;
      }
      this.states.delete(set);
      if (state === 'ready') this.unload(set);
    }
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
      () => {
        if (!this.stale.delete(set)) {
          this.states.set(set, 'ready');
          return;
        }
        this.states.delete(set);
        this.unload(set);
      },
      (error: unknown) => {
        this.stale.delete(set);
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
