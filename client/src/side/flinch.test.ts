import { describe, expect, it } from 'vitest';
import { village } from './content';
import { sideCreatures } from './creatures/creatures';
import { awayFrom, BLINK_HZ, Flinch, FLINCH_SECONDS, HIT_FROM_TILES, reddened } from './flinch';
import { SidePlayer, type Controls } from './player';

const idle: Controls = { x: 0, y: 0, use: false, run: false };
const STREET = { x: 40, y: 15, map: 'high_street' };
const LIGHT = 0xc0b0a0;
const STEP = 1 / 240;

function hold(player: SidePlayer, controls: Controls, seconds: number) {
  for (let t = 0; t < seconds - 1e-9; t += 1 / 60) player.update(controls, 1 / 60);
}

/** Seconds into the flinch of its last red blink. */
function lastRed(flinch: Flinch): number {
  let red = -1;
  for (let t = 0; t < 2; t += STEP) {
    if (flinch.tint(LIGHT) !== LIGHT) red = t;
    flinch.update(STEP);
  }
  return red;
}

const flinched = (strength: number) => {
  const flinch = new Flinch();
  flinch.hit({ size: strength / 10, strength });
  return flinch;
};

describe('flinching', () => {
  it('is away from the nearest creature on their map, else back from the way they face', () => {
    const rat = (x: number, map = 'high_street') => ({ at: { x }, map });
    expect(awayFrom(STREET, 'east', [rat(41), rat(38.5)])).toBe(-1);
    expect(awayFrom(STREET, 'east', [rat(39)])).toBe(1);
    expect(awayFrom(STREET, 'east', [rat(39, 'metro'), rat(40 - HIT_FROM_TILES - 1)])).toBe(-1);
    expect(awayFrom(STREET, 'west', [])).toBe(1);
  });

  it('blinks the figure red, for longer the harder the hit', () => {
    expect(reddened(LIGHT)).toBe(0xc02626);
    const bat = flinched(0.3);
    expect(bat.tint(LIGHT)).toBe(reddened(LIGHT));
    bat.update(1 / (2 * BLINK_HZ));
    expect(bat.tint(LIGHT)).toBe(LIGHT);
    expect(new Flinch().tint(LIGHT)).toBe(LIGHT);
    expect(lastRed(flinched(1))).toBeGreaterThan(lastRed(flinched(0.3)));
    expect(lastRed(flinched(1))).toBeLessThan(FLINCH_SECONDS.most);
    expect(lastRed(flinched(1))).toBeGreaterThan(FLINCH_SECONDS.most - 1 / BLINK_HZ);
  });

  it('knocks them back a little, further the harder the hit, and the arrows can’t steer it', () => {
    sideCreatures.reset([
      { id: 'bot_1', kind: 'bot', position: { x: 41, y: 15, map: 'high_street' }, facing: 'west', state: 'attacking' },
    ]);
    const knocked = (strength: number, controls = idle) => {
      const player = new SidePlayer(village, STREET);
      new Flinch().hit({ size: strength / 10, strength }, player);
      expect(player.airborne).toBe(true);
      expect(player.drawn.facing).toBe('east');
      for (let t = 0; t < 0.5 && player.airborne; t += 1 / 60) player.update(controls, 1 / 60);
      expect(player.airborne).toBe(false);
      return STREET.x - player.position.x;
    };
    const bat = knocked(0.3);
    const bot = knocked(1);
    expect(bat).toBeGreaterThan(0.3);
    expect(bot).toBeGreaterThan(bat);
    expect(bot).toBeLessThan(1.5);
    expect(knocked(1, { ...idle, x: 1 })).toBeCloseTo(bot);
    sideCreatures.reset([]);
  });

  it('leaves them where they are on the stairs, only blinking', () => {
    const player = new SidePlayer(village, { x: 15, y: 2, map: 'coffee_shop_floor_0' });
    hold(player, { ...idle, y: -1 }, 0.5);
    expect(player.climbing).toBe('stairs');
    const on = { ...player.at };
    new Flinch().hit({ size: 0.1, strength: 1 }, player);
    expect(player.airborne).toBe(false);
    expect(player.at).toEqual(on);
  });
});
