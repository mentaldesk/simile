import { describe, expect, it } from 'vitest';
import { server, type Entity, type SnapshotMessage } from '../net';
import { world, WorldModel } from './model';
import { WALKING_SPEED } from './tuning';

const ENTITIES: Entity[] = [
  { id: 'mei', kind: 'npc', name: 'Mei Lin', position: { x: 3, y: 11 } },
  { id: 'viktor', kind: 'npc', name: 'Viktor Hale', position: { x: 10, y: 11 } },
  { id: 'player', kind: 'player', name: 'Player', position: { x: 31, y: 22 } },
];

describe('WorldModel', () => {
  it('places everyone from the snapshot', () => {
    const model = new WorldModel();
    model.reset(ENTITIES);
    expect([...model.npcs.keys()]).toEqual(['mei', 'viktor']);
    expect(model.positionOf('mei')).toEqual({ x: 3, y: 11, map: 'village' });
    expect(model.positionOf('player')).toEqual({ x: 31, y: 22, map: 'village' });
    expect(model.positionOf('nobody')).toBeUndefined();
  });

  it('walks NPCs to where they move', () => {
    const model = new WorldModel();
    model.reset(ENTITIES);
    model.move('mei', { x: 4, y: 11 });
    model.update(0.5);
    expect(model.positionOf('mei')?.x).toBeCloseTo(3 + 0.5 * WALKING_SPEED);
  });

  it('ignores moves of the player and of unknown entities', () => {
    const model = new WorldModel();
    model.reset(ENTITIES);
    model.move('player', { x: 32, y: 22 });
    model.move('tom', { x: 1, y: 1 });
    model.update(1);
    expect(model.positionOf('player')).toEqual({ x: 31, y: 22, map: 'village' });
    expect(model.npcs.has('tom')).toBe(false);
  });

  it('keeps the player where it is on a later snapshot, and replaces the NPCs', () => {
    const model = new WorldModel();
    model.reset(ENTITIES);
    model.player!.place({ x: 20, y: 5 });
    model.reset([
      { id: 'suki', kind: 'npc', name: 'Suki Tan', position: { x: 46, y: 11 } },
      ENTITIES[2],
    ]);
    expect(model.positionOf('player')).toEqual({ x: 20, y: 5, map: 'village' });
    expect([...model.npcs.keys()]).toEqual(['suki']);
  });

  it('shows only the NPCs on the map the player is on, snapping them across a door', () => {
    const model = new WorldModel();
    model.reset([
      ...ENTITIES,
      { id: 'suki', kind: 'npc', name: 'Suki Tan', position: { x: 5, y: 6, map: 'coffee_shop' } },
    ]);
    expect([...model.here()].map(({ id }) => id)).toEqual(['mei', 'viktor']);
    expect(model.positionOf('suki')).toBeUndefined();

    model.move('mei', { x: 31, y: 11, map: 'village' });
    model.move('mei', { x: 10, y: 13, map: 'coffee_shop' });
    model.move('suki', { x: 31, y: 11, map: 'village' });
    expect([...model.here()].map(({ id }) => id)).toEqual(['viktor', 'suki']);
    expect(model.positionOf('mei')).toBeUndefined();
    expect(model.positionOf('suki')).toEqual({ x: 31, y: 11, map: 'village' });
  });

  it('shows the NPCs on the map the player goes to, and only them', () => {
    const model = new WorldModel();
    model.reset([
      ...ENTITIES,
      { id: 'suki', kind: 'npc', name: 'Suki Tan', position: { x: 5, y: 6, map: 'coffee_shop' } },
    ]);
    model.player!.place({ x: 10, y: 13, map: 'coffee_shop' });
    expect(model.map).toBe('coffee_shop');
    expect([...model.here()].map(({ id }) => id)).toEqual(['suki']);
    expect(model.positionOf('suki')).toEqual({ x: 5, y: 6, map: 'coffee_shop' });
    expect(model.positionOf('mei')).toBeUndefined();
    expect(model.positionOf('player')).toEqual({ x: 10, y: 13, map: 'coffee_shop' });

    model.player!.place({ x: 31, y: 11, map: 'village' });
    expect([...model.here()].map(({ id }) => id)).toEqual(['mei', 'viktor']);
  });

  it('knows where everyone is on every map, for audio', () => {
    const model = new WorldModel();
    model.reset([
      ...ENTITIES,
      { id: 'suki', kind: 'npc', name: 'Suki Tan', position: { x: 5, y: 6, map: 'coffee_shop' } },
    ]);
    model.move('suki', { x: 5, y: 7, map: 'coffee_shop' });
    model.update(0.25);
    expect(model.whereIs('suki')).toEqual({ x: 5, y: 6 + 0.25 * WALKING_SPEED, map: 'coffee_shop' });
    expect(model.whereIs('player')).toEqual({ x: 31, y: 22, map: 'village' });
    expect(model.whereIs('nobody')).toBeUndefined();
  });

  it('lets the first snapshot put the player inside', () => {
    const model = new WorldModel();
    model.spawnPlayer({ x: 31, y: 22 });
    model.reset([{ ...ENTITIES[2], position: { x: 10, y: 12, map: 'coffee_shop' } }]);
    expect(model.map).toBe('coffee_shop');
  });

  it('lets the first snapshot move a player spawned before it', () => {
    const model = new WorldModel();
    model.spawnPlayer({ x: 1, y: 1 });
    model.reset(ENTITIES);
    expect(model.positionOf('player')).toEqual({ x: 31, y: 22, map: 'village' });
  });

  it('follows the server from when it loads', () => {
    const snapshot: SnapshotMessage = {
      type: 'snapshot',
      time: '2026-03-14T09:10:03Z',
      map_id: 'village',
      entities: ENTITIES,
      conversations: [],
    };
    server.dispatch(JSON.stringify(snapshot));
    server.dispatch(
      JSON.stringify({ type: 'entity_moved', entity_id: 'viktor', position: { x: 11, y: 11 } }),
    );
    world.update(1 / WALKING_SPEED);
    expect(world.positionOf('viktor')).toEqual({ x: 11, y: 11, map: 'village' });
  });

  it("keeps each NPC's pose and facing, standing facing south-east when the server leaves them out", () => {
    const model = new WorldModel();
    const posture = (id: string) => {
      const npc = model.npcs.get(id)!;
      return [npc.pose, npc.facing];
    };
    model.reset([{ ...ENTITIES[0], pose: 'sitting', facing: 'west' }, ...ENTITIES.slice(1)]);
    expect(posture('mei')).toEqual(['sitting', 'west']);
    expect(posture('viktor')).toEqual(['standing', 'south_east']);

    model.move('mei', { x: 4, y: 11 }, 'walking', 'east');
    expect(posture('mei')).toEqual(['walking', 'east']);
    model.move('mei', { x: 5, y: 11 });
    expect(posture('mei')).toEqual(['standing', 'south_east']);
  });

  it('takes poses and facings from the server', () => {
    const snapshot = { type: 'snapshot', time: '2026-03-14T09:10:03Z', map_id: 'village', entities: ENTITIES };
    server.dispatch(JSON.stringify({ ...snapshot, conversations: [] }));
    server.dispatch(
      JSON.stringify({
        type: 'entity_moved',
        entity_id: 'mei',
        position: { x: 3, y: 11 },
        pose: 'reading',
        facing: 'north',
      }),
    );
    expect(world.npcs.get('mei')).toMatchObject({ pose: 'reading', facing: 'north' });
  });
});
