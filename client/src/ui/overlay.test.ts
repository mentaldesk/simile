import { describe, expect, it } from 'vitest';
import { fitOverlay, inOverlay } from './overlay';
import type { WorldView } from './world-view';

describe('fitOverlay', () => {
  it('scales the overlay on a native canvas to the window, not the device pixels', () => {
    const fit = fitOverlay({ width: 1920, height: 1080 }, { width: 3840, height: 2160 });

    expect(fit).toEqual({ scale: 3, width: 640, height: 360, fromGame: 1 / 6 });
  });

  it('lays out more room on the side the window is longer', () => {
    expect(fitOverlay({ width: 1440, height: 900 }, { width: 2880, height: 1800 })).toMatchObject({
      scale: 2.25,
      width: 640,
      height: 400,
    });
    expect(fitOverlay({ width: 2560, height: 1080 }, { width: 2560, height: 1080 })).toMatchObject({
      scale: 3,
      width: 853,
      height: 360,
    });
  });

  it('never shrinks text below its size in a 640 x 360 window', () => {
    const fit = fitOverlay({ width: 500, height: 400 }, { width: 1000, height: 800 });

    expect(fit).toEqual({ scale: 1, width: 500, height: 400, fromGame: 0.5 });
  });
});

describe('inOverlay', () => {
  const scene: WorldView = {
    positionOf: (id) => (id === 'mei' ? { x: 3, y: 4 } : undefined),
    npcIds: () => ['mei'],
    bubbleAnchor: (id) => (id === 'mei' ? { x: 600, y: 300 } : undefined),
    spriteOf: (id) =>
      id === 'mei' ? { box: { x: 552, y: 300, width: 96, height: 144 }, depth: 9 } : undefined,
  };

  it('maps anchors and boxes from game-canvas pixels to overlay pixels', () => {
    const view = inOverlay(scene, 1 / 6);

    expect(view.bubbleAnchor('mei')).toEqual({ x: 100, y: 50 });
    expect(view.spriteOf('mei')?.box).toEqual({ x: 92, y: 50, width: 16, height: 24 });
    expect(view.positionOf('mei')).toEqual({ x: 3, y: 4 });
    expect([...view.npcIds()]).toEqual(['mei']);
    expect(view.bubbleAnchor('nobody')).toBeUndefined();
    expect(view.spriteOf('nobody')).toBeUndefined();
  });
});
