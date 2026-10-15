import { describe, expect, it } from 'vitest';
import { server, type SnapshotMessage } from '../net';
import {
  distanceFromPlayer,
  setWorldView,
  trackedWorld,
  worldView,
  type WorldView,
} from './world-view';

const snapshot: SnapshotMessage = {
  type: 'snapshot',
  time: '2026-03-14T08:05:00Z',
  map_id: 'village',
  entities: [
    { id: 'player', kind: 'player', name: 'Player', position: { x: 14, y: 13 } },
    { id: 'mei', kind: 'npc', name: 'Mei Lin', position: { x: 4, y: 6 } },
    { id: 'viktor', kind: 'npc', name: 'Viktor Hale', position: { x: 11, y: 6 } },
  ],
  conversations: [],
};

describe('the stand-in world view', () => {
  it('follows the snapshot and entity moves', () => {
    server.dispatch(JSON.stringify(snapshot));
    server.dispatch(
      JSON.stringify({ type: 'entity_moved', entity_id: 'mei', position: { x: 11, y: 13 } }),
    );

    expect(worldView()).toBe(trackedWorld);
    expect([...trackedWorld.npcIds()]).toEqual(['mei', 'viktor']);
    expect(trackedWorld.positionOf('mei')).toEqual({ x: 11, y: 13 });
    expect(distanceFromPlayer(trackedWorld, 'mei')).toBe(3);
  });

  it('centres the player on screen and pins bubbles above heads', () => {
    server.dispatch(JSON.stringify(snapshot));
    const { width, height } = trackedWorld.viewport;

    const player = trackedWorld.bubbleAnchor('player')!;
    const viktor = trackedWorld.bubbleAnchor('viktor')!;

    expect(player.x).toBe(width / 2);
    expect(player.y).toBeLessThan(height / 2);
    expect(viktor.x - player.x).toBe((11 - 14) * 48);
    expect(viktor.y - player.y).toBe((6 - 13) * 48);
    expect(trackedWorld.tileAt({ x: viktor.x, y: viktor.y + 72 - 24 })).toEqual({ x: 11, y: 6 });
  });
});

it('uses the world scene once it registers, until it unregisters', () => {
  const scene: WorldView = {
    positionOf: () => undefined,
    npcIds: () => [],
    bubbleAnchor: () => undefined,
  };

  const unregister = setWorldView(scene);
  expect(worldView()).toBe(scene);
  unregister();
  expect(worldView()).toBe(trackedWorld);
});
