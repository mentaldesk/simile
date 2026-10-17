import { describe, expect, it } from 'vitest';
import { characters } from '../assets';
import { WALKING_SPEED } from '../tuning';
import type { Point } from '../view';
import type { CharacterLights } from './lighting';
import { project } from './projection';
import { figureAt, figureBox } from './screen';
import {
  facingFor,
  ISO_FACINGS,
  isoWalkFrames,
  PIXEL_SCALE,
  PIXEL_TEXTURE,
  pixelFrame,
  standingFrame,
  walkTimeScale,
} from './sheets';

const TILE = { width: 96, height: 48, px_per_metre_up: 53.443 };
const lights = Object.values(
  import.meta.glob<CharacterLights>('../../../../content/art/iso/characters/lights.json', {
    eager: true,
    import: 'default',
  }),
)[0];

type Atlas = { frames: Record<string, { frame: { w: number; h: number } }> };

const STEPS: Point[] = [-1, 0, 1].flatMap((x) => [-1, 0, 1].map((y) => ({ x, y })));

describe('facingFor', () => {
  it.each(STEPS.filter(({ x, y }) => x || y))('faces a step of %o the way it goes on screen', (step) => {
    const { x, y } = project(TILE, step);
    const vertical = Math.abs(y) < 1e-9 ? [] : [y > 0 ? 'down' : 'up'];
    const across = Math.abs(x) < 1e-9 ? [] : [x > 0 ? 'right' : 'left'];
    expect(facingFor(step, 'down')).toBe([...vertical, ...across].join('_'));
  });

  it('turns a step between two facings to the nearer one on the map', () => {
    expect(facingFor({ x: 1, y: 0.35 }, 'up')).toBe('down_right');
    expect(facingFor({ x: 1, y: 0.45 }, 'up')).toBe('down');
    expect(facingFor({ x: -0.1, y: -1 }, 'down')).toBe('up_right');
  });

  it('keeps facing the same way standing still', () => {
    expect(facingFor({ x: 0, y: 0 }, 'up_left')).toBe('up_left');
  });
});

describe('pixelFrame', () => {
  it('is the texture at a whole number of scene px per texture px, with the feet at the bottom', () => {
    expect(Number.isInteger(PIXEL_SCALE)).toBe(true);
    for (const scale of [1, 2, 3, 4]) {
      expect(pixelFrame(scale)).toEqual({
        width: 16 * scale,
        height: 24 * scale,
        anchor: { x: 8 * scale, y: 24 * scale },
        figureHeight: 24 * scale,
      });
    }
  });

  it('refuses a scale that would draw texture px unevenly', () => {
    expect(() => pixelFrame(2.5)).toThrow(RangeError);
    expect(() => pixelFrame(0)).toThrow(RangeError);
  });

  it.each([1, 2, 3])('draws each texture px as whole canvas px at zoom %i', (zoom) => {
    const frame = pixelFrame();
    const camera = { width: 1600, height: 1000, zoom, scrollX: -811.5, scrollY: 403.25 };
    const box = figureBox(figureAt({ x: 20.3, y: 18.6 }, TILE, () => 0.18, frame), camera, frame);
    expect(box.width / PIXEL_TEXTURE.width).toBe(PIXEL_SCALE * zoom);
    expect(box.height / PIXEL_TEXTURE.height).toBe(PIXEL_SCALE * zoom);
  });

  it('stands a resident as tall as the figure their drop shadows were measured for', () => {
    const figure = lights.figure_m * TILE.px_per_metre_up;
    expect(Math.abs(pixelFrame().figureHeight - figure)).toBeLessThan(1);
  });
});

describe('the walk', () => {
  it("is in every character's atlas for every facing, at the texture's size", () => {
    expect(characters.length).toBeGreaterThan(0);
    for (const { key, atlas } of characters) {
      const { frames } = atlas as Atlas;
      for (const facing of ISO_FACINGS) {
        for (const name of [...isoWalkFrames(facing), standingFrame(facing)]) {
          expect(frames[name]?.frame, `${key} ${name}`).toMatchObject({
            w: PIXEL_TEXTURE.width,
            h: PIXEL_TEXTURE.height,
          });
        }
      }
    }
  });

  it('steps, stands, steps the other way and stands', () => {
    expect(isoWalkFrames('up_left')).toEqual(['up_left-0', 'up_left-1', 'up_left-2', 'up_left-1']);
    expect(standingFrame('down_right')).toBe('down_right-1');
  });

  it('plays at its own pace at walking speed, and faster or slower with the speed', () => {
    expect(walkTimeScale(WALKING_SPEED)).toBe(1);
    expect(walkTimeScale(2 * WALKING_SPEED)).toBeCloseTo(2);
    expect(walkTimeScale(WALKING_SPEED / 2)).toBeCloseTo(0.5);
  });
});
