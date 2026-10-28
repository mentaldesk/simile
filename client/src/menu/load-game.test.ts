import { describe, expect, it } from 'vitest';
import { worldDetails } from './load-game';

const NOW = Date.parse('2026-10-26T12:00:00Z');

const world = {
  id: 'w',
  name: 'Ash Lane',
  default: false,
  running: false,
  made: '2026-10-20T09:00:00Z',
  played: '2026-10-26T09:00:00Z',
  day: 3,
  time: '2026-10-22T15:00:00Z',
  player: 'Visitor',
  residents: 1,
};

describe('worldDetails', () => {
  it('gives the day, when it was played, the player and the residents', () => {
    expect(worldDetails(world, NOW)).toBe('day 3 · played 3 hours ago · Visitor · 1 resident');
  });

  it('says when a world has never been played', () => {
    expect(worldDetails({ ...world, played: null, day: null, residents: 6 }, NOW)).toBe(
      'not started · never played · Visitor · 6 residents',
    );
  });
});
