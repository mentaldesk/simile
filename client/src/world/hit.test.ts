import { describe, expect, it } from 'vitest';
import type { ScreenPoint, ScreenSprite, WorldView } from '../ui/world-view';
import { framePixel, npcAt, spriteBox } from './hit';

function view(anchors: Record<string, ScreenPoint>): WorldView {
  return {
    positionOf: () => undefined,
    npcIds: () => Object.keys(anchors).filter((id) => id !== 'player'),
    bubbleAnchor: (id) => anchors[id],
  };
}

function drawn(sprites: Record<string, ScreenSprite>): WorldView {
  return {
    positionOf: () => undefined,
    npcIds: () => Object.keys(sprites),
    bubbleAnchor: () => undefined,
    spriteOf: (id) => sprites[id],
  };
}

describe('the top-down fallback', () => {
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
});

describe("the scene's own sprites", () => {
  const box = (x: number, y: number) => ({ x, y, width: 96, height: 144 });

  it('picks the one drawn in front by depth, not by height on screen', () => {
    const crowd = drawn({
      front: { box: box(0, 0), depth: 500 },
      behind: { box: box(20, 10), depth: 480 },
    });

    expect(npcAt({ x: 50, y: 50 }, crowd)).toBe('front');
    expect(npcAt({ x: 110, y: 150 }, crowd)).toBe('behind');
  });

  it('picks one behind through a clear part of the sprite in front', () => {
    const middle = ({ x }: ScreenPoint) => x >= 30 && x < 66;
    const crowd = drawn({
      front: { box: box(0, 100), depth: 500, opaqueAt: middle },
      behind: { box: box(20, 40), depth: 480, opaqueAt: () => true },
    });

    expect(npcAt({ x: 50, y: 110 }, crowd)).toBe('front');
    expect(npcAt({ x: 25, y: 110 }, crowd)).toBe('behind');
    expect(npcAt({ x: 80, y: 110 }, crowd)).toBe('behind');
  });

  it('picks the one in front when the click is clear of both', () => {
    const crowd = drawn({
      behind: { box: box(20, 40), depth: 480, opaqueAt: () => false },
      front: { box: box(0, 100), depth: 500, opaqueAt: () => false },
    });

    expect(npcAt({ x: 50, y: 110 }, crowd)).toBe('front');
    expect(npcAt({ x: 0, y: 0 }, crowd)).toBeUndefined();
  });
});

describe('framePixel', () => {
  const frame = { width: 16, height: 24 };

  it('finds the frame pixel under a point in a box drawn at 6x', () => {
    const box = { x: 100, y: 50, width: 96, height: 144 };

    expect(framePixel({ x: 100, y: 50 }, box, frame)).toEqual({ x: 0, y: 0 });
    expect(framePixel({ x: 105.9, y: 55.9 }, box, frame)).toEqual({ x: 0, y: 0 });
    expect(framePixel({ x: 106, y: 56 }, box, frame)).toEqual({ x: 1, y: 1 });
    expect(framePixel({ x: 195.9, y: 193.9 }, box, frame)).toEqual({ x: 15, y: 23 });
  });
});
