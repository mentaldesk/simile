import { describe, expect, it, vi } from 'vitest';
import { loadMap, mapIds, maps } from './assets';

describe('maps', () => {
  it('has the village, and every interior once loaded', async () => {
    expect([...mapIds].sort()).toEqual(['coffee_shop', 'gallery', 'maker_space', 'noodle_bar', 'village']);
    expect(maps.village?.width).toBe(64);
    expect(maps.noodle_bar).toBeUndefined();

    const json = JSON.stringify({ width: 20, height: 14, tilewidth: 16, tileheight: 16, layers: [] });
    const read = vi.fn(async (url: string) => (url.endsWith('/noodle_bar.tmj') ? json : ''));
    const noodles = await loadMap('noodle_bar', read);
    expect(noodles.width).toBe(20);
    expect(maps.noodle_bar).toBe(noodles);
    expect(await loadMap('noodle_bar', read)).toBe(noodles);
    expect(read).toHaveBeenCalledTimes(1);
  });

  it('has no map it doesn’t know', async () => {
    await expect(loadMap('moon')).rejects.toThrow('No map moon');
  });
});
