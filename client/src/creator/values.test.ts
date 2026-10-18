import { describe, expect, it } from 'vitest';
import valuesPy from '../../../server/simile/npc/values.py?raw';
import {
  ARCHETYPES,
  CORE_VALUES,
  GAIN,
  LATENT_RANGE,
  LOADINGS,
  NOISE,
  TRAITS,
  ValueModel,
  ranked,
} from './values';

function seeded(seed: number): () => number {
  let state = seed;
  return () => {
    state = (state * 1664525 + 1013904223) % 2 ** 32;
    return state / 2 ** 32;
  };
}

describe('the values model', () => {
  it('matches simile.npc.values', () => {
    const loadings = [...valuesPy.matchAll(/V\.(\w+): \(([^)]*)\)/g)].map(([, name, numbers]) => [
      name.toLowerCase(),
      numbers.split(',').map(Number),
    ]);
    expect(Object.fromEntries(loadings)).toEqual(LOADINGS);
    expect(loadings.map(([name]) => name)).toEqual(CORE_VALUES);
    expect(valuesPy).toContain(`TRAITS = (${TRAITS.map((t) => `"${t}"`).join(', ')})`);
    expect(valuesPy).toContain(`GAIN = ${GAIN}`);
    expect(valuesPy).toContain(`NOISE = ${NOISE}`);
  });

  it('gives every value 0.5 for average traits and no quirks', () => {
    const model = new ValueModel(
      ARCHETYPES[0].latent,
      Object.fromEntries(CORE_VALUES.map((v) => [v, 0])) as never,
    );
    expect(new Set(Object.values(model.values()))).toEqual(new Set([0.5]));
  });

  it('moves the values a trait loads on', () => {
    const model = ValueModel.random(seeded(1));
    const before = model.values();
    model.setTrait('openness', 2);
    const after = model.values();
    expect(after.freedom).toBeGreaterThan(before.freedom);
    expect(after.tradition).toBeLessThan(before.tradition);
    expect(after.compassion).toBe(before.compassion);
  });

  it('keeps traits in range', () => {
    const model = ValueModel.random(seeded(2));
    model.setTrait('rigour', 9);
    expect(model.latent.rigour).toBe(LATENT_RANGE);
  });

  it('recovers a character’s values when fitted', () => {
    const original = ValueModel.random(seeded(3));
    original.setLatent({ openness: 1.2, transcendence: -0.5, outlook: 0.3, rigour: -1 });
    const values = original.values();
    const fitted = ValueModel.fit(values);
    expect(fitted.values()).toEqual(values);
    expect(fitted.latent.openness).toBeGreaterThan(0.5);
    expect(fitted.latent.rigour).toBeLessThan(-0.3);
  });

  it('sets one value by hand and keeps it relative to the traits', () => {
    const model = ValueModel.random(seeded(4));
    model.setValue('honesty', 0.9);
    expect(model.values().honesty).toBe(0.9);
    model.setTrait('transcendence', 1);
    expect(model.values().honesty).toBeGreaterThan(0.9);
  });

  it('ranks values from most cared about', () => {
    const model = ValueModel.random(seeded(5));
    model.setValue('justice', 0.99);
    expect(ranked(model.values())[0][0]).toBe('justice');
  });
});
