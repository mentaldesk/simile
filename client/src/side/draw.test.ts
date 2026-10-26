import type Phaser from 'phaser';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { levels, playLevel } from '../world/assets';
import { village } from './content';
import { placeParts } from './draw';
import { spans, stretchWidth, TEXTURE_LIMIT } from './layout';

vi.mock('phaser', () => ({ default: {} }));

type Drawn = { x: number; key: string; originX: number; scale: number };

function fakeScene(drawn: Drawn[]): Phaser.Scene {
  const image = (x: number, _y: number, key: string) => {
    const state: Drawn = { x, key, originX: 0, scale: 1 };
    drawn.push(state);
    const chain = {
      setOrigin: (originX: number) => ((state.originX = originX), chain),
      setScale: (scale: number) => ((state.scale = scale), chain),
    };
    return chain;
  };
  return { add: { image } } as unknown as Phaser.Scene;
}

/** Where each part's texture starts and ends in the world. */
function edges(drawn: Drawn[], widths: number[]): [number, number][] {
  return drawn.map(({ x, originX, scale }, i) => [x - originX * widths[i] * scale, x + (1 - originX) * widths[i] * scale]);
}

describe('a picture wider than a texture can be', () => {
  afterEach(() => playLevel(0));

  const widest = Math.max(
    ...Object.keys(levels).map((level) => {
      playLevel(Number(level));
      return stretchWidth(village.map('sewers')!.furniture.find(({ name }) => name === 'sewer_vault')!);
    }),
  );

  it("draws the widest level's vault as parts that meet edge to edge across its full width", () => {
    expect(widest).toBeGreaterThan(TEXTURE_LIMIT);
    const parts = spans(widest).map(({ x, width }) => ({ key: `vault~${x}`, x, width }));
    const drawn: Drawn[] = [];
    placeParts(fakeScene(drawn), { scale: 1, pad: 0, parts }, { width: widest, height: 276 }, [0.5, 1], 1000, 0);

    expect(drawn.map(({ key }) => key)).toEqual(parts.map(({ key }) => key));
    const at = edges(drawn, parts.map(({ width }) => width));
    expect(at[0][0]).toBeCloseTo(1000 - widest / 2);
    for (let i = 1; i < at.length; i++) expect(at[i][0]).toBeCloseTo(at[i - 1][1]);
    expect(at.at(-1)![1]).toBeCloseTo(1000 + widest / 2);
  });

  it('draws its shadow, made smaller and padded, back at full size with its parts meeting too', () => {
    const [scale, pad] = [0.5, 20];
    const texture = Math.ceil(widest * scale) + 2 * pad;
    const parts = spans(texture, 4096).map(({ x, width }) => ({ key: `shadow~${x}`, x, width }));
    const drawn: Drawn[] = [];
    placeParts(fakeScene(drawn), { scale, pad, parts }, { width: widest, height: 276 }, [0.5, 1], 1000, 0);

    const at = edges(drawn, parts.map(({ width }) => width));
    expect(at[0][0]).toBeCloseTo(1000 - widest / 2 - pad / scale);
    for (let i = 1; i < at.length; i++) expect(at[i][0]).toBeCloseTo(at[i - 1][1]);
    expect(at.at(-1)![1]).toBeCloseTo(at[0][0] + texture / scale);
  });
});
