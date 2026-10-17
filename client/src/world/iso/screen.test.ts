import { describe, expect, it } from 'vitest';
import { overheardMix, SILENT_BEYOND } from '../../audio/spatial';
import type { Position } from '../../net';
import type { WorldView } from '../../ui/world-view';
import { npcAt } from '../hit';
import { residentDepth } from './depth';
import { feetOf, project } from './projection';
import { figureAt, figureBox, screenAligned, type IsoCamera } from './screen';
import { FIGURE_HEIGHT, FIGURE_WIDTH } from './tuning';

const TILE = { width: 96, height: 48, px_per_metre_up: 53.443 };
const flat = () => 0;

function cameraOn(zoom: number): IsoCamera {
  const centre = project(TILE, { x: 20.5, y: 20.5 });
  const [width, height] = [1600, 1000];
  return { width, height, zoom, scrollX: centre.x - width / 2, scrollY: centre.y - height / 2 };
}

describe('figureAt', () => {
  it('stands on the middle of its tile, raised by the ground, sorted on the ground plane', () => {
    const feet = project(TILE, feetOf({ x: 20, y: 20 }));
    const figure = figureAt({ x: 20, y: 20 }, TILE, () => 0.18);

    expect(figure.x).toBe(feet.x);
    expect(figure.bottom).toBeCloseTo(feet.y - 0.18 * TILE.px_per_metre_up);
    expect(figure.bottom - figure.top).toBe(FIGURE_HEIGHT);
    expect(figure.depth).toBe(residentDepth(feetOf({ x: 20, y: 20 }), TILE));
  });
});

describe('figureBox', () => {
  it.each([1, 2, 3])('covers the sprite through the camera at zoom %i', (zoom) => {
    const camera = cameraOn(zoom);
    const box = figureBox(figureAt({ x: 20, y: 20 }, TILE, flat), camera);

    expect(box.width).toBe(FIGURE_WIDTH * zoom);
    expect(box.height).toBe(FIGURE_HEIGHT * zoom);
    expect(box.x + box.width / 2).toBe(camera.width / 2);
    expect(box.y + box.height).toBe(camera.height / 2);
  });

  it("puts the bubble anchor at the feet's screen position less the sprite's height", () => {
    const camera = cameraOn(2);
    const feet = project(TILE, feetOf({ x: 22, y: 19 }), 0.18);
    const box = figureBox(figureAt({ x: 22, y: 19 }, TILE, () => 0.18), camera);
    const onCanvas = (at: number, scroll: number, size: number) =>
      (at - scroll - size / 2) * 2 + size / 2;

    expect(box.x + box.width / 2).toBeCloseTo(onCanvas(feet.x, camera.scrollX, camera.width));
    expect(box.y).toBeCloseTo(onCanvas(feet.y, camera.scrollY, camera.height) - FIGURE_HEIGHT * 2);
  });
});

describe('iso picking', () => {
  function crowd(positions: Record<string, Position>, heights: Record<string, number> = {}) {
    const camera = cameraOn(2);
    const view: WorldView = {
      positionOf: (id) => positions[id],
      npcIds: () => Object.keys(positions),
      bubbleAnchor: () => undefined,
      spriteOf: (id) => {
        const figure = figureAt(positions[id], TILE, () => heights[id] ?? 0);
        return { box: figureBox(figure, camera), depth: figure.depth };
      },
    };
    return { view, boxOf: (id: string) => view.spriteOf!(id)!.box };
  }

  it('picks a resident by their body, standing up to 1.5 tiles above their tile', () => {
    const { view, boxOf } = crowd({ mei: { x: 20, y: 20 } });
    const box = boxOf('mei');
    const [x, feet, tile] = [box.x + box.width / 2, box.y + box.height, TILE.height * 2];

    expect(npcAt({ x, y: feet - 1.4 * tile }, view)).toBe('mei');
    expect(npcAt({ x, y: feet - 1.6 * tile }, view)).toBeUndefined();
    expect(npcAt({ x, y: feet + 4 }, view)).toBeUndefined();
  });

  it('picks the one in front where one stands behind the other on screen', () => {
    const { view, boxOf } = crowd({ behind: { x: 20, y: 20 }, front: { x: 21, y: 21 } });
    const behind = boxOf('behind');
    const front = boxOf('front');
    const overlap = { x: front.x + front.width / 2, y: (front.y + behind.y + behind.height) / 2 };

    expect(front.y).toBeLessThan(behind.y + behind.height);
    expect(npcAt(overlap, view)).toBe('front');
    expect(npcAt({ x: behind.x + behind.width / 2, y: behind.y + 4 }, view)).toBe('behind');
  });

  it('goes by depth where grass lifts the one in front above the one behind on a road', () => {
    const positions = { behind: { x: 20, y: 20 }, front: { x: 20.1, y: 20.1 } };
    const { view, boxOf } = crowd(positions, { front: 0.18, behind: -0.08 });

    expect(boxOf('front').y).toBeLessThan(boxOf('behind').y);
    expect(npcAt({ x: boxOf('front').x + 40, y: boxOf('behind').y + 40 }, view)).toBe('front');
  });
});

describe('screenAligned', () => {
  const listener = { x: 20, y: 20 };
  const heard = (dx: number, dy: number) =>
    overheardMix(screenAligned(listener)!, screenAligned({ x: 20 + dx, y: 20 + dy })!);

  it('keeps distances in tiles, so earshot is unchanged', () => {
    for (const [dx, dy] of [[3, 0], [0, -4], [2, 2], [-5, 1.5]]) {
      const turned = screenAligned({ x: 20 + dx, y: 20 + dy })!;
      const centre = screenAligned(listener)!;
      expect(Math.hypot(turned.x - centre.x, turned.y - centre.y)).toBeCloseTo(Math.hypot(dx, dy));
    }
    expect(heard(0, SILENT_BEYOND + 0.1).gain).toBe(0);
    expect(heard(0, SILENT_BEYOND - 0.1).gain).toBeGreaterThan(0);
    expect(heard(2, 2).gain).toBeCloseTo(overheardMix(listener, { x: 22, y: 22 }).gain);
  });

  it('pans by where a speaker is on screen', () => {
    expect(heard(2, -2).pan).toBeCloseTo(0.8);
    expect(heard(-2, 2).pan).toBeCloseTo(-0.8);
    expect(heard(3, 3).pan).toBeCloseTo(0);
    expect(heard(-3, -3).pan).toBeCloseTo(0);
    expect(screenAligned(undefined)).toBeUndefined();
  });
});
