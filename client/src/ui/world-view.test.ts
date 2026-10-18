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

  it('leaves out NPCs on another map than the player’s', () => {
    server.dispatch(
      JSON.stringify({
        ...snapshot,
        entities: [
          ...snapshot.entities,
          { id: 'suki', kind: 'npc', name: 'Suki Tan', position: { x: 14, y: 14, map: 'coffee_shop' } },
        ],
      }),
    );
    expect([...trackedWorld.npcIds()]).toEqual(['mei', 'viktor']);
    expect(trackedWorld.positionOf('suki')).toBeUndefined();
    expect(distanceFromPlayer(trackedWorld, 'suki')).toBeUndefined();

    server.dispatch(
      JSON.stringify({ type: 'entity_moved', entity_id: 'suki', position: { x: 14, y: 14, map: 'village' } }),
    );
    expect(distanceFromPlayer(trackedWorld, 'suki')).toBe(1);
  });

  it('measures no distance between maps, whatever the view', () => {
    const view: WorldView = {
      positionOf: (id) => (id === 'player' ? { x: 5, y: 6, map: 'coffee_shop' } : { x: 5, y: 7 }),
      npcIds: () => ['mei'],
      bubbleAnchor: () => undefined,
      spriteOf: () => undefined,
    };
    expect(distanceFromPlayer(view, 'mei')).toBeUndefined();
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

  it('draws a 48 x 72 box below each bubble anchor', () => {
    server.dispatch(JSON.stringify(snapshot));
    const viktor = trackedWorld.bubbleAnchor('viktor')!;

    expect(trackedWorld.spriteOf('viktor')).toEqual({
      box: { x: viktor.x - 24, y: viktor.y, width: 48, height: 72 },
      depth: viktor.y + 72,
    });
    expect(trackedWorld.spriteOf('nobody')).toBeUndefined();
  });

  it('scales its tiles and boxes to the game canvas', () => {
    server.dispatch(JSON.stringify(snapshot));
    const at = (scale: number) => {
      trackedWorld.scale = scale;
      const player = trackedWorld.bubbleAnchor('player')!;
      const viktor = trackedWorld.spriteOf('viktor')!.box;
      return { ...viktor, x: viktor.x - player.x, y: viktor.y - player.y };
    };

    const [one, three] = [at(1), at(3)];
    trackedWorld.scale = 1;

    expect(three).toEqual({ x: 3 * one.x, y: 3 * one.y, width: 144, height: 216 });
  });
});

it('uses the world scene once it registers, until it unregisters', () => {
  const scene: WorldView = {
    positionOf: () => undefined,
    npcIds: () => [],
    bubbleAnchor: () => undefined,
    spriteOf: () => undefined,
  };

  const unregister = setWorldView(scene);
  expect(worldView()).toBe(scene);
  unregister();
  expect(worldView()).toBe(trackedWorld);
});
