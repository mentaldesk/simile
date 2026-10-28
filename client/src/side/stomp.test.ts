import { describe, expect, it } from 'vitest';
import type { Creature, CreatureKind } from '../net';
import { village } from './content';
import { Tracked } from './creatures/creatures';
import { SidePlayer, type Controls } from './player';
import { STOMP_TOP, stompedOn } from './stomp';

const STREET = { x: 10, y: 15, map: 'high_street' };
const BACK = STREET.y - STOMP_TOP;

const creature = (kind: CreatureKind, x = STREET.x, map = STREET.map): Tracked =>
  new Tracked({ id: `${kind}_1`, kind, position: { x, y: STREET.y, map }, facing: 'east', state: 'idle' } satisfies Creature);

describe('landing on a rat', () => {
  it('stops the feet on the back of a rat they come down onto, and nothing else', () => {
    const on = (creatures: Tracked[], x = STREET.x, from = 13, to = 15) => stompedOn(creatures, STREET.map, x, from, to);
    expect(on([creature('rat')])).toBe(BACK);
    expect(on([creature('rat')], STREET.x + 0.5)).toBe(BACK);
    expect(on([creature('rat')], STREET.x + 1)).toBeUndefined();
    expect(on([creature('rat')], STREET.x, 15, 15)).toBeUndefined();
    expect(on([creature('rat')], STREET.x, 13, 14)).toBeUndefined();
    expect(on([creature('rat', STREET.x, 'metro')])).toBeUndefined();
    expect(on([creature('dog'), creature('bot'), creature('bat')])).toBeUndefined();
    const gone = creature('rat');
    gone.down = 0;
    expect(on([gone])).toBeUndefined();
  });

  it('bounces the player off it, and says so until the scene has sent where', () => {
    const player = new SidePlayer(village, STREET);
    const rat = creature('rat', STREET.x);
    player.stomps = (map, x, from, to) => stompedOn([rat], map, x, from, to);
    const idle: Controls = { x: 0, y: 0, use: false, run: false };
    player.update({ ...idle, jump: true, hold: true }, 1 / 60);
    for (let frame = 0; frame < 120 && !player.bounced; frame++) player.update({ ...idle, hold: true }, 1 / 60);

    expect(player.bounced).toBe(true);
    expect(player.position.y).toBeCloseTo(BACK, 6);
    player.update(idle, 1 / 60);
    expect(player.position.y).toBeLessThan(BACK);
    expect(player.airborne).toBe(true);
  });

  it('walks into a rat without bouncing', () => {
    const player = new SidePlayer(village, { ...STREET, x: STREET.x - 2 });
    const rat = creature('rat', STREET.x);
    player.stomps = (map, x, from, to) => stompedOn([rat], map, x, from, to);
    for (let frame = 0; frame < 60; frame++) player.update({ x: 1, y: 0, use: false, run: false }, 1 / 60);

    expect(player.position.x).toBeGreaterThan(STREET.x);
    expect(player.bounced).toBe(false);
    expect(player.position.y).toBe(STREET.y);
  });
});
