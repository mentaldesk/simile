import { describe, expect, it, vi } from 'vitest';
import { PPM } from './layout';
import { SHADOW_LOOK, shadowSpread } from './textures';

vi.mock('phaser', () => ({ default: {} }));

describe('the runtime shadow', () => {
  it('is cast where it always was, at full strength, unless the look says otherwise', () => {
    expect(SHADOW_LOOK).toEqual({ opacity: 1, offset: { x: 0, y: 0 } });
    expect(shadowSpread(SHADOW_LOOK, 0.5, 8)).toEqual({ pad: 20, dx: 0, dy: 0 });
    expect(shadowSpread(SHADOW_LOOK, 0.25, 5)).toEqual({ pad: 13, dx: 0, dy: 0 });
  });

  it("moves on by the look's offset in metres, with room for it round the picture", () => {
    const look = { opacity: 0.5, offset: { x: -0.1, y: 0.05 } };
    const { pad, dx, dy } = shadowSpread(look, 0.5, 8);
    expect(dx / 0.5).toBeCloseTo(-0.1 * PPM);
    expect(dy / 0.5).toBeCloseTo(0.05 * PPM);
    expect(pad).toBeGreaterThanOrEqual(20 + Math.abs(dx));
  });
});
