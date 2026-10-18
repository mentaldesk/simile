import { describe, expect, it } from 'vitest';
import { Idle, Talkers } from './idle';
import type { IdleTuning } from './tuning';

const TUNING: IdleTuning = {
  shiftEvery: [4, 4],
  shiftFor: 0.5,
  turnTiles: 3,
  glanceEvery: [10, 10],
  glanceFor: [2, 2],
};
const nobody = () => false;

const bodies = (at: Record<string, [number, number]>) =>
  new Map(Object.entries(at).map(([id, [x, y]]) => [id, { position: { x, y } }]));

function run(idle: Idle, seconds: number, step = 0.1): boolean[] {
  const shifted: boolean[] = [];
  for (let t = 0; t < seconds - 1e-9; t += step) {
    idle.update(step);
    shifted.push(idle.shifted);
  }
  return shifted;
}

describe('Idle', () => {
  it('shifts its weight now and then, for a moment', () => {
    const idle = new Idle(TUNING, () => 0.5);
    const shifted = run(idle, 9);
    const starts = shifted.flatMap((on, i) => (on && !shifted[i - 1] ? [(i + 1) * 0.1] : []));
    expect(starts).toHaveLength(2);
    expect(starts[0]).toBeCloseTo(4, 1);
    expect(starts[1] - starts[0]).toBeCloseTo(TUNING.shiftFor + 4, 0);
    expect(shifted.filter(Boolean).length).toBe(10);
  });

  it('starts afresh once they move off', () => {
    const idle = new Idle(TUNING, () => 0.5);
    run(idle, 4.05);
    expect(idle.shifted).toBe(true);
    idle.reset();
    expect(idle.shifted).toBe(false);
  });

  it('turns to whoever near is talking, the nearest of them', () => {
    const idle = new Idle(TUNING, () => 0.5);
    const everyone = bodies({ mei: [5, 5], ada: [6, 5], kofi: [5, 7], tobias: [5, 2.5], far: [9, 5] });
    const talking = (id: string) => id !== 'ada';
    expect(idle.towards('mei', { x: 5, y: 5 }, everyone, talking)).toEqual({ x: 0, y: 2 });
    expect(idle.towards('mei', { x: 5, y: 5 }, everyone, (id) => id === 'far')).toBeUndefined();
  });

  it('glances at whoever is nearest now and then, then faces its own way again', () => {
    const idle = new Idle(TUNING, () => 0.5);
    const everyone = bodies({ mei: [5, 5], ada: [4, 5] });
    const look = () => idle.towards('mei', { x: 5, y: 5 }, everyone, nobody);
    expect(look()).toBeUndefined();
    run(idle, 10.05);
    expect(look()).toEqual({ x: -1, y: 0 });
    run(idle, 2);
    expect(look()).toBeUndefined();
  });

  it('keeps glancing at the same person while they stay near', () => {
    const idle = new Idle(TUNING, () => 0.5);
    const everyone = bodies({ mei: [5, 5], ada: [4, 5] });
    run(idle, 10.05);
    expect(idle.towards('mei', { x: 5, y: 5 }, everyone, nobody)).toEqual({ x: -1, y: 0 });
    everyone.set('kofi', { position: { x: 5, y: 4.5 } });
    expect(idle.towards('mei', { x: 5, y: 5 }, everyone, nobody)).toEqual({ x: -1, y: 0 });
  });
});

describe('Talkers', () => {
  it('counts a speaker as talking for as long as their line lasts', () => {
    const talkers = new Talkers();
    talkers.heard('mei', 2, 1000);
    expect(talkers.talking('mei', 2900)).toBe(true);
    expect(talkers.talking('mei', 3100)).toBe(false);
    expect(talkers.talking('ada', 1000)).toBe(false);
  });
});
