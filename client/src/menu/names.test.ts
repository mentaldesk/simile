import { describe, expect, it } from 'vitest';
import { suggestName } from './names';

const sequence = (...values: number[]) => {
  let at = 0;
  return () => values[at++ % values.length];
};

describe('suggestName', () => {
  it('names a world like a street', () => {
    expect(suggestName([], sequence(0, 0))).toBe('Ash Close');
    expect(suggestName([])).toMatch(/^[A-Z]\w+ [A-Z]\w+$/);
  });

  it('never suggests a name a world has', () => {
    expect(suggestName(['ash close'], sequence(0, 0, 0, 0.99))).toBe('Ash Yard');
  });
});
