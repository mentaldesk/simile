import { describe, expect, it } from 'vitest';
import type { Creature } from '../net';
import { attackerOf, HIT_FROM_TILES } from './attacker';
import { Tracked } from './creatures/creatures';

const PLAYER = { x: 40, y: 15, map: 'high_street' };

const rat = (x: number, more: Partial<Creature> = {}, y = 15): Tracked =>
  new Tracked({ id: `rat_${x}_${y}`, kind: 'rat', position: { x, y, map: 'high_street' }, facing: 'east', state: 'chasing', ...more });

const down = (tracked: Tracked) => Object.assign(tracked, { down: 0.1 });

describe('what hit the player', () => {
  it('is the nearest creature on their map within reach', () => {
    const near = rat(38.5);
    expect(attackerOf(PLAYER, [rat(41.8), near])).toBe(near);
    expect(attackerOf(PLAYER, [rat(39, { position: { x: 39, y: 15, map: 'metro' } }), rat(40 - HIT_FROM_TILES - 0.5)])).toBeUndefined();
    expect(attackerOf(undefined, [near])).toBeUndefined();
  });

  it('is the one attacking over a nearer one, counts rows as well as tiles, and never one going down', () => {
    const attacking = rat(41.5, { state: 'attacking' });
    expect(attackerOf(PLAYER, [rat(39.5), attacking])).toBe(attacking);
    const along = rat(38.5);
    expect(attackerOf(PLAYER, [rat(40.3, {}, 17.9), along])).toBe(along);
    expect(attackerOf(PLAYER, [rat(40.5, {}, 18.5)])).toBeUndefined();
    expect(attackerOf(PLAYER, [down(rat(40.5, { state: 'attacking' })), along])).toBe(along);
  });
});
