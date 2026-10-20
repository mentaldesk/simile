import { describe, expect, it } from 'vitest';
import { dollFor, dolls, mapIds, maps } from './assets';

describe('maps', () => {
  it('has every street and floor, bundled', () => {
    expect(mapIds).toContain('high_street');
    expect(mapIds).toContain('banyan_row');
    expect(mapIds).toContain('coffee_shop_floor_0');
    expect(mapIds).toContain('house_10_floor_1');
    expect(mapIds).not.toContain('village');
    expect(maps.high_street?.width).toBe(84);
    expect(maps.gallery_floor_2?.properties).toContainEqual({ name: 'view', type: 'string', value: 'side' });
  });
});

describe('dollFor', () => {
  it('is their own doll, or the same resident’s every time for anyone without one', () => {
    expect(dollFor('kofi')).toBe(dolls.kofi);
    expect(dollFor('player')).toBe(dolls.player);
    const stranger = dollFor('wren_abernethy');
    expect(dollFor('wren_abernethy')).toBe(stranger);
    expect(stranger).not.toBe(dolls.player);
    expect(Object.values(dolls)).toContain(stranger);
  });
});
