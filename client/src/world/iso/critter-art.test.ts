import { describe, expect, it } from 'vitest';
import palettePy from '../../../../server/simile/art/palette.py?raw';
import {
  CRITTER_BOXES,
  CRITTER_PALETTE,
  critterSheet,
  DUCK_POSES,
  duckFrame,
  HERON_POSES,
  heronFrame,
  PLUMAGES,
  rippleFrame,
  RIPPLES,
  type SheetFrame,
} from './critter-art';

const sheet = critterSheet();
const a1 = Object.fromEntries(
  [...palettePy.slice(0, palettePy.indexOf('}')).matchAll(/"(\w+)": "(#[0-9a-f]{6})"/g)].map(([, name, hex]) => [
    name,
    hex,
  ]),
);

const hexAt = (x: number, y: number) => {
  const i = (y * sheet.width + x) * 4;
  return sheet.rgba[i + 3] === 0
    ? undefined
    : '#' + [...sheet.rgba.slice(i, i + 3)].map((value) => value.toString(16).padStart(2, '0')).join('');
};

const frameNamed = (name: string) => sheet.frames.find((frame) => frame.name === name)!;

function pixelsOf({ kind, x, y }: SheetFrame): (string | undefined)[][] {
  const { width, height } = CRITTER_BOXES[kind];
  return Array.from({ length: height }, (_, row) =>
    Array.from({ length: width }, (_, column) => hexAt(x + column, y + row)),
  );
}

describe('critterSheet', () => {
  it('uses only A1’s palette, fully opaque', () => {
    expect(Object.keys(a1)).toHaveLength(32);
    for (const [name, hex] of Object.entries(CRITTER_PALETTE)) expect(a1[name]).toBe(hex);
    const used = new Set<string>();
    for (let i = 0; i < sheet.rgba.length; i += 4) {
      expect([0, 255]).toContain(sheet.rgba[i + 3]);
      const hex = hexAt((i / 4) % sheet.width, Math.floor(i / 4 / sheet.width));
      if (hex) used.add(hex);
    }
    expect([...used].every((hex) => Object.values(a1).includes(hex))).toBe(true);
  });

  it('has every frame the critters draw, and no others', () => {
    const names = [
      ...PLUMAGES.flatMap((plumage) =>
        DUCK_POSES.flatMap((pose) => [duckFrame(plumage, pose, 'left'), duckFrame(plumage, pose, 'right')]),
      ),
      ...HERON_POSES.flatMap((pose) => [heronFrame(pose, 'left'), heronFrame(pose, 'right')]),
      ...RIPPLES.map(rippleFrame),
    ];
    expect(sheet.frames.map(({ name }) => name).sort()).toEqual(names.sort());
  });

  it('packs the frames side by side, inside the sheet', () => {
    const covered = new Uint8Array(sheet.width * sheet.height);
    for (const { kind, x, y } of sheet.frames) {
      const { width, height } = CRITTER_BOXES[kind];
      expect(x + width).toBeLessThanOrEqual(sheet.width);
      expect(y + height).toBeLessThanOrEqual(sheet.height);
      for (let row = y; row < y + height; row++) {
        for (let column = x; column < x + width; column++) expect(covered[row * sheet.width + column]++).toBe(0);
      }
    }
  });

  it('is small', () => {
    expect(sheet.width * sheet.height * 4).toBeLessThan(64 * 1024);
  });

  it('mirrors each left-facing frame to face right', () => {
    for (const frame of sheet.frames.filter(({ name }) => name.endsWith('-left'))) {
      const right = pixelsOf(frameNamed(frame.name.replace(/-left$/, '-right')));
      expect(pixelsOf(frame).map((row) => [...row].reverse())).toEqual(right);
    }
  });

  it('outlines the birds in ink, as A1 outlines characters', () => {
    const edges = new Set([CRITTER_PALETTE.ink, CRITTER_PALETTE.ice, CRITTER_PALETTE.white]);
    for (const frame of sheet.frames.filter(({ kind }) => kind !== 'ripple')) {
      const pixels = pixelsOf(frame);
      pixels.forEach((row, y) =>
        row.forEach((hex, x) => {
          const clear = [pixels[y - 1]?.[x], pixels[y + 1]?.[x], row[x - 1], row[x + 1]].some((next) => !next);
          if (hex && clear) expect(edges).toContain(hex);
        }),
      );
    }
  });
});
