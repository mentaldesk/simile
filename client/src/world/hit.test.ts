import { expect, it } from 'vitest';
import type { ScreenPoint, WorldView } from '../ui/world-view';
import { npcAt, spriteBox } from './hit';

function view(anchors: Record<string, ScreenPoint>): WorldView {
  return {
    positionOf: () => undefined,
    npcIds: () => Object.keys(anchors).filter((id) => id !== 'player'),
    bubbleAnchor: (id) => anchors[id],
  };
}

it('covers the 48 x 72 sprite below its bubble anchor', () => {
  expect(spriteBox('kofi', view({ kofi: { x: 100, y: 50 } }))).toEqual({
    x: 76,
    y: 50,
    width: 48,
    height: 72,
  });
  expect(spriteBox('nobody', view({}))).toBeUndefined();
});

it.each([
  [{ x: 100, y: 60 }, 'kofi'],
  [{ x: 76, y: 121 }, 'kofi'],
  [{ x: 124, y: 60 }, undefined],
  [{ x: 100, y: 49 }, undefined],
  [{ x: 100, y: 122 }, undefined],
])('finds the NPC at %o', (point, expected) => {
  expect(npcAt(point, view({ kofi: { x: 100, y: 50 } }))).toBe(expected);
});

it('picks the NPC in front where sprites overlap, and never the player', () => {
  const crowd = view({
    behind: { x: 100, y: 40 },
    front: { x: 110, y: 60 },
    player: { x: 100, y: 80 },
  });

  expect(npcAt({ x: 100, y: 100 }, crowd)).toBe('front');
  expect(npcAt({ x: 100, y: 50 }, crowd)).toBe('behind');
});
