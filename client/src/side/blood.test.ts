import { describe, expect, it } from 'vitest';
import { alphaOf, Blood, BLOOD, CHEST_M, LIFE_SECONDS } from './blood';
import { PPM } from './layout';

const FEET = { x: 1000, y: 2000 };

/** A random that walks through `values`, over and over. */
const cycling = (...values: number[]) => {
  let i = 0;
  return () => values[i++ % values.length];
};

function run(blood: Blood, seconds: number, step = 1 / 60) {
  for (let t = 0; t < seconds - 1e-9; t += step) blood.update(step);
}

describe('blood', () => {
  it('bursts a few drops from the chest, more and bigger the harder the hit', () => {
    const bat = new Blood();
    bat.burst(0.3, FEET, FEET.y, 0, cycling(0.5));
    const bot = new Blood();
    bot.burst(1, FEET, FEET.y, 0, cycling(0.5));
    expect(bat.drops).toHaveLength(Math.round(BLOOD.drops.least + (BLOOD.drops.most - BLOOD.drops.least) * 0.3));
    expect(bot.drops).toHaveLength(BLOOD.drops.most);
    expect(bot.drops[0].radius).toBeGreaterThan(bat.drops[0].radius);
    expect(bot.drops[0].y).toBeCloseTo(FEET.y - CHEST_M * PPM);
  });

  it('flies away from what hit them, falls and fades', () => {
    const blood = new Blood();
    blood.burst(1, FEET, FEET.y, -1, cycling(0.2, 0.5, 0.8));
    expect(blood.drops.every(({ vy }) => vy < 0)).toBe(true);
    expect(blood.drops.reduce((sum, { vx }) => sum + vx, 0)).toBeLessThan(0);
    const from = blood.drops.map(({ y }) => y);
    run(blood, LIFE_SECONDS.least - 0.05);
    expect(blood.drops.some(({ y }, i) => y > from[i])).toBe(true);
    expect(Math.max(...blood.drops.map(alphaOf))).toBeLessThan(1);
    run(blood, LIFE_SECONDS.most);
    expect(blood.drops).toEqual([]);
  });

  it('settles on the ground under them rather than falling through it', () => {
    const blood = new Blood();
    blood.burst(1, FEET, FEET.y, 0, cycling(0.5, 0.5, 0.5, 0, 0.5, 1));
    run(blood, LIFE_SECONDS.most - 0.05);
    expect(blood.drops.length).toBeGreaterThan(0);
    expect(blood.drops.every(({ landed, y }) => landed && y === FEET.y)).toBe(true);
  });

  it('falls past the feet of a player hit in the air, to the ground under them', () => {
    const ground = FEET.y + 0.3 * PPM;
    const blood = new Blood();
    blood.burst(1, FEET, ground, 0, cycling(0.5, 0.5, 0.5, 0, 0.5, 1));
    run(blood, LIFE_SECONDS.most - 0.05);
    expect(blood.drops.length).toBeGreaterThan(0);
    expect(blood.drops.every(({ landed, y }) => landed && y === ground)).toBe(true);
  });

  it('clears, for another street', () => {
    const blood = new Blood();
    blood.burst(1, FEET, FEET.y, 0);
    blood.clear();
    expect(blood.drops).toEqual([]);
  });
});
