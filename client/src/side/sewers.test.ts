import { afterEach, describe, expect, it } from 'vitest';
import { server } from '../net';
import { levels, maps, playLevel } from '../world/assets';
import { interactablesOn } from '../world/interactables';
import { village } from './content';

const snapshot = (level?: number) =>
  server.dispatch(JSON.stringify({ type: 'snapshot', time: '2026-01-01T10:00:00Z', map_id: 'high_street', entities: [], conversations: [], level }));

describe("the sewers' levels", () => {
  afterEach(() => playLevel(0));

  it('bundles eight, each a map of the sewers, and plays level 0 until the snapshot names one', () => {
    expect(Object.keys(levels).map(Number)).toEqual([0, 1, 2, 3, 4, 5, 6, 7]);
    for (const level of Object.values(levels)) expect(Object.keys(level)).toEqual(['sewers']);
    expect(maps.sewers).toBe(levels[0].sewers);
  });

  it("plays the snapshot's level: its map, its links and its hatch", () => {
    snapshot(5);

    expect(maps.sewers).toBe(levels[5].sewers);
    expect(village.map('sewers')!.width).toBe(levels[5].sewers.width);
    const [up] = village.map('sewers')!.links;
    expect(village.far(up)).toMatchObject({ map: 'metro', x: 100, y: 15 });
    expect(interactablesOn('sewers').map(({ id }) => id)).toContain('sewers_hatch');
  });

  it('keeps level 0 for a snapshot from a server without levels', () => {
    snapshot(5);
    snapshot();

    expect(maps.sewers).toBe(levels[0].sewers);
  });
});
