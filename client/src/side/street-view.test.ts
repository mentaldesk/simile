import type Phaser from 'phaser';
import { describe, expect, it, vi } from 'vitest';
import { pieceUrl, scenery, village } from './content';
import { DEPTH } from './depths';
import { TILE } from './layout';
import { emptyLight } from './light';
import { StreetView } from './street-view';
import type { SideTextures } from './textures';

vi.mock('phaser', () => ({ default: { BlendModes: { ADD: 1 } } }));

type Drawn = { x: number; y: number; depth: number; alpha: number; visible: boolean };

/** Every image the street adds, keeping its depth, alpha and visibility; any other call chains. */
function fakeScene(drawn: Drawn[]): Phaser.Scene {
  const add = (x = 0, y = 0) => {
    const state: Drawn = { x, y, depth: 0, alpha: 1, visible: true };
    drawn.push(state);
    const set: Record<string, (value: never) => void> = {
      setDepth: (depth: number) => (state.depth = depth),
      setAlpha: (alpha: number) => (state.alpha = alpha),
      setVisible: (visible: boolean) => (state.visible = visible),
      setY: (y: number) => (state.y = y),
    };
    const image: object = new Proxy(state, {
      get: (target, name: string) =>
        name in target ? target[name as keyof Drawn] : (value: never) => (set[name]?.(value), image),
    });
    return image;
  };
  const size = { width: 100, height: 100, realWidth: 100, realHeight: 100 };
  return {
    add: { image: add, rectangle: add, nineslice: add },
    textures: { get: () => ({ getSourceImage: () => size }), getFrame: () => size },
    sys: { isActive: () => true },
  } as unknown as Phaser.Scene;
}

const fakeTextures = {
  key: (key: string) => `side:${key}`,
  tileFrame: () => ({ frame: 'tile', x: 0, width: 100 }),
  bottomColour: () => 0,
  ...Object.fromEntries(
    ['shadow', 'light', 'blurred', 'stretched', 'band'].map((name) => [
      name,
      (key: string) => ({ key: `side:${key}#${name}`, name: `${key}#${name}`, scale: 1, pad: 0 }),
    ]),
  ),
  ...Object.fromEntries(['lamp', 'signpost', 'exitSign', 'roomShade', 'contact'].map((name) => [name, () => name])),
} as unknown as SideTextures;

function highStreet() {
  const drawn: Drawn[] = [];
  const map = village.map('high_street')!;
  const street = new StreetView(fakeScene(drawn), fakeTextures, { village, scenery, pieceUrl }, map);
  const props = drawn.filter(({ depth }) => depth === DEPTH.streetFurniture);
  const cafe = map.buildings.find(({ name }) => name === 'coffee_shop')!;
  const inFront = (x: number) => x >= cafe.x * TILE && x <= (cafe.x + cafe.w) * TILE;
  const view = { x: 0, y: 0, width: 2000, height: 2000, centerX: 1000, centerY: 1000, bottom: 2000 };
  const update = (open: string | undefined) =>
    street.update(view as Phaser.Geom.Rectangle, emptyLight(), false, open, 0.1);
  return { street, props, inFront, update };
}

describe('the street in front of a dollhouse', () => {
  it('leaves out the props in front while it opens, is open and closes, and brings them back', () => {
    const { street, props, inFront, update } = highStreet();
    const front = props.filter(({ x }) => inFront(x));
    const rest = props.filter(({ x }) => !inFront(x));
    expect(front.length).toBeGreaterThanOrEqual(4);
    expect(rest.length).toBeGreaterThan(0);

    update('coffee_shop');
    expect(street.isOpen('coffee_shop')).toBe(true);
    expect(front.every(({ visible }) => !visible)).toBe(true);
    for (let i = 0; i < 10; i++) update('coffee_shop');
    expect(front.every(({ visible }) => !visible)).toBe(true);
    expect(rest.every(({ visible }) => visible)).toBe(true);

    update(undefined);
    expect(street.isOpen('coffee_shop')).toBe(true);
    expect(front.every(({ visible }) => !visible)).toBe(true);
    for (let i = 0; i < 10; i++) update(undefined);
    expect(street.isOpen('coffee_shop')).toBe(false);
    expect(props.every(({ visible }) => visible)).toBe(true);
  });

  it('never draws a street prop see-through', () => {
    const { props, update } = highStreet();
    for (const open of ['coffee_shop', 'coffee_shop', undefined, 'noodle_bar', undefined]) {
      for (let i = 0; i < 3; i++) update(open);
      expect(props.every(({ alpha }) => alpha === 1)).toBe(true);
    }
  });

  it('says a resident there is left out, as poses.hiddenInFront reads it, only while the front is off', () => {
    const { street, inFront, update } = highStreet();
    const [there, elsewhere] = [30.5 * TILE, 50.5 * TILE];
    expect(inFront(there) && !inFront(elsewhere)).toBe(true);
    expect(street.ghost(there)).toBe(1);
    update('coffee_shop');
    expect(street.ghost(there)).toBeLessThan(1);
    expect(street.ghost(elsewhere)).toBe(1);
    for (let i = 0; i < 10; i++) update('coffee_shop');
    expect(street.ghost(there)).toBe(0);
  });
});
