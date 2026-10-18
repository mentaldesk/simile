import type { Values } from './character';

export const TRAITS = ['openness', 'transcendence', 'outlook', 'rigour'] as const;
export type Trait = (typeof TRAITS)[number];
export type Latent = Record<Trait, number>;

type Loading = readonly [number, number, number, number];

export const LOADINGS = {
  freedom: [0.85, 0.0, 0.1, -0.2],
  independence: [0.7, -0.3, 0.0, 0.1],
  self_respect: [0.2, -0.4, 0.1, 0.3],
  self_actualization: [0.6, 0.1, 0.2, 0.2],
  creativity: [0.75, 0.1, 0.2, -0.2],
  honesty: [0.0, 0.5, 0.0, 0.4],
  compassion: [0.0, 0.85, 0.2, 0.0],
  loyalty: [-0.4, 0.5, 0.0, 0.3],
  justice: [0.2, 0.7, 0.0, 0.2],
  responsibility: [-0.4, 0.3, 0.0, 0.6],
  security: [-0.75, -0.1, -0.3, 0.2],
  equality: [0.3, 0.75, 0.1, -0.1],
  tradition: [-0.85, 0.2, 0.0, 0.1],
  obedience: [-0.85, 0.0, 0.0, 0.3],
  success: [-0.1, -0.8, 0.1, 0.3],
  ambition: [0.2, -0.8, 0.2, 0.3],
  discipline: [-0.4, -0.1, 0.0, 0.75],
  knowledge: [0.5, 0.2, 0.0, 0.4],
  open_mindedness: [0.75, 0.4, 0.1, -0.1],
  peace_of_mind: [-0.4, 0.3, 0.2, -0.1],
  pleasure: [0.4, -0.4, 0.4, -0.6],
  connection: [0.0, 0.6, 0.5, 0.0],
  adventure: [0.8, -0.2, 0.4, -0.3],
  optimism: [0.1, 0.1, 0.9, 0.0],
} as const satisfies Record<string, Loading>;

export type CoreValue = keyof typeof LOADINGS;
export const CORE_VALUES = Object.keys(LOADINGS) as CoreValue[];
export type Quirks = Record<CoreValue, number>;

export const GAIN = 1.2;
export const NOISE = 0.6;
export const LATENT_RANGE = 2.5;
const EDGE = 0.001;

export const TRAIT_ENDS: Record<Trait, [string, string]> = {
  openness: ['Holds to what they know', 'Goes after the new'],
  transcendence: ['Looks after themselves', 'Looks after others'],
  outlook: ['Expects the worst', 'Expects the best'],
  rigour: ['Goes with the flow', 'Keeps to the plan'],
};

export type Archetype = { name: string; blurb: string; latent: Latent };

export const ARCHETYPES: Archetype[] = [
  archetype('Average', 'Nothing pulls them far either way', 0, 0, 0, 0),
  archetype('Free spirit', 'Restless, warm, unbothered by rules', 1.6, 0.3, 0.8, -1.2),
  archetype('Pillar', 'Dutiful, loyal, keeps things as they were', -1.3, 0.8, 0.2, 1.2),
  archetype('Go-getter', 'Driven, disciplined, out for themselves', 0.4, -1.5, 0.6, 1.0),
  archetype('Carer', 'Puts other people first, every time', 0, 1.6, 0.6, 0.3),
  archetype('Idealist', 'Open-minded and set on fairness', 1.2, 1.4, 0.4, 0),
  archetype('Cynic', 'Expects little from anyone', 0, -0.8, -1.6, 0.2),
  archetype('Traditionalist', 'Faith in custom and doing it properly', -1.8, 0, -0.2, 0.8),
];

function archetype(name: string, blurb: string, ...z: [number, number, number, number]) {
  return { name, blurb, latent: latent(...z) };
}

function latent(openness: number, transcendence: number, outlook: number, rigour: number): Latent {
  return { openness, transcendence, outlook, rigour };
}

export const AVERAGE: Latent = latent(0, 0, 0, 0);

/** Values as four shared traits plus a quirk per value, as P3 samples them. */
export class ValueModel {
  latent: Latent;
  quirks: Quirks;

  constructor(latent: Latent, quirks: Quirks) {
    this.latent = { ...latent };
    this.quirks = { ...quirks };
  }

  static random(random: () => number = Math.random): ValueModel {
    const quirks = Object.fromEntries(CORE_VALUES.map((v) => [v, gauss(random) * NOISE]));
    return new ValueModel(AVERAGE, quirks as Quirks);
  }

  static fit(values: Values): ValueModel {
    const y = CORE_VALUES.map((v) => logit(values[v] ?? 0.5));
    const a = CORE_VALUES.map((v) => LOADINGS[v].map((w) => GAIN * w));
    const ata = TRAITS.map((_, i) => TRAITS.map((_, j) => sum(a.map((row) => row[i] * row[j]))));
    const aty = TRAITS.map((_, i) => sum(a.map((row, k) => row[i] * y[k])));
    const z = solve(ata, aty);
    const fitted = Object.fromEntries(TRAITS.map((t, i) => [t, round(z[i], 2)])) as Latent;
    const model = new ValueModel(fitted, {} as Quirks);
    for (const [k, v] of CORE_VALUES.entries()) model.quirks[v] = y[k] - model.pull(v);
    return model;
  }

  values(): Record<CoreValue, number> {
    return Object.fromEntries(
      CORE_VALUES.map((v) => [v, round(logistic(this.pull(v) + this.quirks[v]), 2)]),
    ) as Record<CoreValue, number>;
  }

  setTrait(trait: Trait, z: number): void {
    this.latent[trait] = clamp(z, -LATENT_RANGE, LATENT_RANGE);
  }

  setLatent(latent: Latent): void {
    for (const trait of TRAITS) this.setTrait(trait, latent[trait]);
  }

  setValue(value: CoreValue, score: number): void {
    this.quirks[value] = logit(score) - this.pull(value);
  }

  copy(): ValueModel {
    return new ValueModel(this.latent, this.quirks);
  }

  private pull(value: CoreValue): number {
    return GAIN * sum(LOADINGS[value].map((w, i) => w * this.latent[TRAITS[i]]));
  }
}

export function ranked(values: Values): [CoreValue, number][] {
  return CORE_VALUES.map((v): [CoreValue, number] => [v, values[v] ?? 0]).sort(
    (a, b) => b[1] - a[1],
  );
}

export function label(value: string): string {
  const words = value.replaceAll('_', ' ');
  return words[0].toUpperCase() + words.slice(1);
}

function solve(m: number[][], b: number[]): number[] {
  const n = b.length;
  const rows = m.map((row, i) => [...row, b[i]]);
  for (let col = 0; col < n; col++) {
    let pivot = col;
    for (let r = col + 1; r < n; r++) {
      if (Math.abs(rows[r][col]) > Math.abs(rows[pivot][col])) pivot = r;
    }
    [rows[col], rows[pivot]] = [rows[pivot], rows[col]];
    for (let r = 0; r < n; r++) {
      if (r === col) continue;
      const factor = rows[r][col] / rows[col][col];
      for (let c = col; c <= n; c++) rows[r][c] -= factor * rows[col][c];
    }
  }
  return rows.map((row, i) => row[n] / row[i]);
}

function gauss(random: () => number): number {
  const u = 1 - random();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * random());
}

function logistic(x: number): number {
  return 1 / (1 + Math.exp(-x));
}

function logit(p: number): number {
  const q = clamp(p, EDGE, 1 - EDGE);
  return Math.log(q / (1 - q));
}

function sum(xs: number[]): number {
  return xs.reduce((a, b) => a + b, 0);
}

function clamp(x: number, low: number, high: number): number {
  return Math.min(high, Math.max(low, x));
}

export function round(x: number, places: number): number {
  const scale = 10 ** places;
  return Math.round(x * scale) / scale;
}
