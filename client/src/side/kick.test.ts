import { describe, expect, it } from 'vitest';
import { village } from './content';
import { kick, KICK_PHASE, KICK_SECONDS } from './kick';
import { SidePlayer, type Controls } from './player';

const idle: Controls = { x: 0, y: 0, use: false, eTaken: false, run: false };
const street = () => new SidePlayer(village, { x: 10, y: 15, map: 'high_street' });

describe('kicking', () => {
  it('kicks the way they last walked, even facing up after', () => {
    const player = street();
    expect(player.kick()).toBe('east');
    player.update(idle, KICK_SECONDS);
    player.update({ ...idle, x: -1 }, 0.1);
    player.update({ ...idle, y: -1 }, 1 / 60);
    expect(player.kick()).toBe('west');
    expect(player.drawn).toMatchObject({ pose: 'walking', phase: KICK_PHASE, run: 1, facing: 'west' });
  });

  it('stands still for the kick, and kicks again only once it is done', () => {
    const player = street();
    player.kick();
    player.update({ ...idle, x: 1 }, KICK_SECONDS / 2);
    expect(player.position.x).toBe(10);
    expect(player.kick()).toBeUndefined();
    player.update(idle, KICK_SECONDS / 2);
    expect(player.drawn.pose).toBe('standing');
    expect(player.kick()).toBe('east');
  });

  it("doesn't kick in the air", () => {
    const player = street();
    player.update({ ...idle, jump: true, hold: true }, 1 / 60);
    expect(player.airborne).toBe(true);
    expect(player.kick()).toBeUndefined();
  });

  it('tells the server which way, and leaves what it hits to the server', () => {
    expect(kick('west')).toEqual({ type: 'kick', facing: 'west' });
  });
});
