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
    expect(model.positionOf('mei')).toEqual({ x: 3, y: 11 });
    expect(model.positionOf('player')).toEqual({ x: 31, y: 22 });
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
    expect(model.positionOf('player')).toEqual({ x: 31, y: 22 });
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
    expect(model.positionOf('player')).toEqual({ x: 20, y: 5 });
    expect([...model.npcs.keys()]).toEqual(['suki']);
  });

  it('lets the first snapshot move a player spawned before it', () => {
    const model = new WorldModel();
    model.spawnPlayer({ x: 1, y: 1 });
    model.reset(ENTITIES);
    expect(model.positionOf('player')).toEqual({ x: 31, y: 22 });
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
    expect(world.positionOf('viktor')).toEqual({ x: 11, y: 11 });
  });
});
