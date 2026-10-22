import { describe, expect, it } from 'vitest';
import { village } from './content';
import { bareSockets } from './plugs';

describe('bareSockets', () => {
  it('draws a socket at each plug in the village, on the street cell in front of it', () => {
    expect(bareSockets(village, village.map('high_street')!)).toEqual([
      { x: 15, y: 15, inside: true },
      { x: 41, y: 15, inside: true },
      { x: 66, y: 15, inside: true },
    ]);
  });

  it("leaves the metro's plug to its breaker box", () => {
    expect(bareSockets(village, village.map('metro')!)).toEqual([]);
  });
});
