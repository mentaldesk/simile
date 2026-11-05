import type Phaser from 'phaser';
import { describe, expect, it, vi } from 'vitest';
import { LAYER_PLACES, layerCopies, parallaxY, streetCentreY } from './camera';
import { pieceUrl, scenery, village } from './content';
import { DEPTH } from './depths';
import { MOULDING } from './house';
import { furniturePlacement, GROUND_LIFT_M, PPM, streetRow, TILE } from './layout';
import { emptyLight, lightAt } from './light';
import type { SceneryManifest } from './scenery';
import { CITY_PARALLAX, LAMP_HEAD_M, StreetView } from './street-view';
import type { SideTextures } from './textures';

vi.mock('phaser', () => ({ default: { BlendModes: { ADD: 1 } } }));

type Drawn = { x: number; y: number; key: unknown; depth: number; alpha: number; visible: boolean; args: unknown[] };

/** Every image the street adds, keeping where it is, its depth, alpha and visibility; any other call chains. */
function fakeScene(drawn: Drawn[]): Phaser.Scene {
  const add = (x = 0, y = 0, ...args: unknown[]) => {
    const state: Drawn = { x, y, key: args[0], depth: 0, alpha: 1, visible: true, args };
    drawn.push(state);
    const set: Record<string, (...values: never[]) => void> = {
      setDepth: (depth: number) => (state.depth = depth),
      setAlpha: (alpha: number) => (state.alpha = alpha),
      setVisible: (visible: boolean) => (state.visible = visible),
      setY: (y: number) => (state.y = y),
      setPosition: (x: number, y: number) => ([state.x, state.y] = [x, y]),
    };
    const image: object = new Proxy(state, {
      get: (target, name: string) =>
        name in target ? target[name as keyof Drawn] : (...values: never[]) => (set[name]?.(...values), image),
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
  parts: (key: string) => [{ key: `side:${key}`, x: 0, width: 100 }],
  size: () => ({ width: 100, height: 100 }),
  ...Object.fromEntries(
    ['shadow', 'light', 'blurred', 'stretched', 'band'].map((name) => [
      name,
      (key: string) => {
        const parts = [{ key: `side:${key}#${name}`, x: 0, width: 100 }];
        return { key: `side:${key}#${name}`, name: `${key}#${name}`, scale: 1, pad: 0, parts };
      },
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

const map = (id: string) => village.map(id)!;
const view = (centerX: number, centerY: number) =>
  ({ x: centerX - 1000, y: centerY - 1000, width: 2000, height: 2000, centerX, centerY, bottom: centerY + 1000 }) as Phaser.Geom.Rectangle;

function drawStreet(id: string, manifest: SceneryManifest = scenery) {
  const drawn: Drawn[] = [];
  const street = new StreetView(fakeScene(drawn), fakeTextures, { village, scenery: manifest, pieceUrl }, map(id));
  const at = (depth: number) => drawn.filter((image) => image.depth === depth);
  return { street, drawn, at };
}

const STREETS = village.streets.map(({ id }) => id);
const UNDER = village.streets.filter(({ underground }) => underground).map(({ id }) => id);
const CITY = [DEPTH.city, DEPTH.cityHaze, DEPTH.landmark, DEPTH.landmarkHaze, DEPTH.landmarkGlow];

describe("today's manifest", () => {
  it('draws the city and one Apex on every street above ground, and none under it', () => {
    expect(UNDER).toEqual(expect.arrayContaining(['metro', 'sewers']));
    for (const id of STREETS) {
      const { street, at } = drawStreet(id);
      street.update(view(3000, 1500), lightAt(23, scenery), true, undefined, 0.1);
      if (UNDER.includes(id)) {
        for (const depth of CITY) expect(at(depth), id).toEqual([]);
      } else {
        expect(at(DEPTH.city).length, id).toBeGreaterThan(0);
        expect(at(DEPTH.landmark), id).toHaveLength(1);
      }
    }
  });

  it('measures what the constants say', () => {
    expect(scenery.parallax.city).toBe(CITY_PARALLAX);
    expect(scenery.furniture.lamp.light).toBe(LAMP_HEAD_M);
    expect(scenery.furniture.picture_frame.moulding).toEqual(MOULDING);
  });
});

/** Today's manifest without P69's measurements, the grounds' `surface` or `parallax.city`. */
function bare(): SceneryManifest {
  const manifest = structuredClone(scenery);
  delete manifest.parallax.city;
  for (const entry of Object.values(manifest.furniture)) {
    for (const field of ['seat', 'bed', 'light', 'moulding'] as const) delete entry[field];
  }
  for (const piece of Object.values(manifest.pieces)) delete piece.surface;
  return manifest;
}

describe('a manifest without measurements', () => {
  it('lights each street lamp LAMP_HEAD_M up, and nothing else', () => {
    for (const id of STREETS) {
      const lamps = map(id).furniture.filter(({ name }) => name === 'lamp');
      const heads = lamps.map((lamp) => furniturePlacement(lamp, map(id)).y - LAMP_HEAD_M * PPM);
      expect(drawStreet(id, bare()).at(DEPTH.lampGlow).map(({ y }) => y), id).toEqual(heads);
    }
  });

  it('draws the ground with its walking edge GROUND_LIFT_M above the feet line', () => {
    const feet = streetRow(map('high_street')) * TILE;
    const tops = drawStreet('high_street', bare()).at(DEPTH.ground).map(({ y }) => y);
    expect(tops).toContain(feet - GROUND_LIFT_M * PPM);
  });

  it('frames the paintings with MOULDING', () => {
    const { drawn } = drawStreet('banyan_row', bare());
    const frames = drawn.filter(({ key }) => key === 'side:furniture/picture_frame').map(({ args }) => args.slice(4, 8));
    expect(frames.length).toBeGreaterThan(0);
    for (const sides of frames) expect(sides).toEqual([MOULDING.left, MOULDING.right, MOULDING.top, MOULDING.bottom]);
  });
});

/** A bare manifest with a city on every street, the Apex towers, and measurements. */
function measured(parallax?: number): SceneryManifest {
  const manifest = bare();
  if (parallax !== undefined) manifest.parallax.city = parallax;
  const piece = (kind: 'layer' | 'sprite' | 'glow', size: [number, number], height: number) => ({
    file: `fixture/${kind}.webp`,
    size,
    height,
    kind,
    anchor: [0.5, 1] as [number, number],
  });
  manifest.pieces['fixture/city'] = piece('layer', [2400, 840], 7);
  manifest.pieces['fixture/apex'] = piece('sprite', [960, 936], 7.8);
  manifest.pieces['fixture/apex-glow'] = piece('glow', [960, 936], 7.8);
  for (const layers of Object.values(manifest.streets)) layers.city = 'fixture/city';
  const at = Object.fromEntries(STREETS.map((id) => [id, 0.25]));
  manifest.landmarks = { apex: { piece: 'fixture/apex', glow: 'fixture/apex-glow', at } };
  manifest.pieces[manifest.streets.high_street.ground].surface = 0.2;
  manifest.furniture.lamp.light = 3;
  manifest.furniture.bench.light = 1.2;
  manifest.furniture.picture_frame.moulding = { left: 20, right: 21, top: 22, bottom: 23 };
  return manifest;
}

describe('a manifest with a city, a landmark and measurements', () => {
  const manifest = measured(0.15);
  const street = (id = 'high_street') => {
    const drawn = drawStreet(id, manifest);
    const feet = streetRow(map(id)) * TILE;
    const width = map(id).width * TILE;
    const apex = () => drawn.at(DEPTH.landmark)[0];
    const city = () => drawn.at(DEPTH.city).filter(({ visible }) => visible);
    const update = (x: number, y = streetCentreY(feet, { width: 2000, height: 2000 }), hour = 13) =>
      drawn.street.update(view(x, y), lightAt(hour, scenery), true, undefined, 0.1);
    return { ...drawn, feet, width, apex, city, update };
  };

  it('lists the city and the landmark among the pieces to load above ground only', () => {
    const content = { village, scenery: manifest, pieceUrl };
    for (const piece of ['fixture/city', 'fixture/apex', 'fixture/apex-glow']) {
      expect(StreetView.pieces(content, map('high_street'))).toContain(piece);
      for (const id of UNDER) expect(StreetView.pieces(content, map(id))).not.toContain(piece);
    }
  });

  /** Where the first copy of a tile as wide as the fake's goes. */
  const firstCopy = (parallax: number, x: number) =>
    layerCopies(parallax, 100, { left: x - 1000, width: 2000, centre: { x, y: 0 } }, 0, 0, { first: 0, count: 0, y: 0 }).first;

  it('draws the city between the sky and the far layer, tiled at parallax.city', () => {
    const { city, update, feet } = street();
    update(4037);
    expect(city().length).toBeGreaterThan(0);
    expect(DEPTH.sky < DEPTH.city && DEPTH.cityHaze < DEPTH.far).toBe(true);
    expect(city()[0].x).toBeCloseTo(firstCopy(0.15, 4037));
    expect(city()[0].x).not.toBeCloseTo(firstCopy(manifest.parallax.far, 4037));
    expect(city()[0].y).toBeCloseTo(feet + LAYER_PLACES.city.bottom * PPM);
  });

  it('falls back to a parallax of 0.1 for a manifest without parallax.city', () => {
    const drawn = drawStreet('high_street', measured());
    drawn.street.update(view(4037, 1000), lightAt(13, scenery), true, undefined, 0.1);
    expect(CITY_PARALLAX).toBe(0.1);
    expect(drawn.at(DEPTH.city)[0].x).toBeCloseTo(firstCopy(CITY_PARALLAX, 4037));
  });

  it('draws the landmark once, in the middle of the view when its centre is at `at`, behind the city', () => {
    const { at, apex, update, width } = street();
    expect(at(DEPTH.landmark)).toHaveLength(1);
    expect(DEPTH.landmarkGlow < DEPTH.city).toBe(true);
    update(0.25 * width);
    expect(apex().x).toBeCloseTo(0.25 * width);
    update(0.25 * width + 1000);
    expect(apex().x - (0.25 * width + 1000)).toBeCloseTo(-1000 * 0.15);
    update(0.25 * width - 2000);
    expect(apex().x - (0.25 * width - 2000)).toBeCloseTo(2000 * 0.15);
  });

  it('stands the landmark on the city layer bottom edge, above the street, as the view rises and falls', () => {
    const { apex, city, update, feet } = street();
    const level = streetCentreY(feet, { width: 2000, height: 2000 });
    for (const y of [level, level - 12 * PPM, level + 3 * PPM]) {
      update(4000, y);
      expect(apex().y).toBeCloseTo(city()[0].y);
      expect(apex().y).toBeCloseTo(parallaxY(0.15, feet + LAYER_PLACES.city.bottom * PPM, y, level));
      expect(apex().y).toBeLessThan(feet);
    }
  });

  it('lights the landmark in full at night, at 55% in the evening, and not by day', () => {
    const { at, update } = street();
    const glows = () => at(DEPTH.landmarkGlow);
    expect(glows()).toHaveLength(2);
    update(4000, 1000, 23);
    expect(glows()[0]).toMatchObject({ visible: true, alpha: 1 });
    update(4000, 1000, 19);
    expect(glows()[0]).toMatchObject({ visible: true, alpha: 0.55 });
    update(4000, 1000, 13);
    expect(glows()[0].visible).toBe(false);
  });

  it('hazes the landmark as the city', () => {
    const { at, update } = street();
    update(4000, 1000, 23);
    update(4000, 1000, 23);
    const [haze] = at(DEPTH.landmarkHaze);
    const [cityHaze] = at(DEPTH.cityHaze).filter(({ visible }) => visible);
    expect(haze.alpha).toBeGreaterThan(0);
    expect(haze.alpha).toBe(cityHaze.alpha);
  });

  it('draws no city or landmark under the village, whatever the manifest says', () => {
    for (const id of UNDER) {
      const { at, update } = street(id);
      update(3000, 1500, 23);
      for (const depth of CITY) expect(at(depth), id).toEqual([]);
    }
  });

  it("lights every piece with a light that far up, the lamp's from the manifest", () => {
    const { at } = street();
    const items = map('high_street').furniture.filter(({ name }) => name === 'lamp' || name === 'bench');
    expect(items.some(({ name }) => name === 'bench')).toBe(true);
    const heads = items.map((item) => furniturePlacement(item, map('high_street')).y - (item.name === 'lamp' ? 3 : 1.2) * PPM);
    expect(at(DEPTH.lampGlow).map(({ y }) => y)).toEqual(heads);
  });

  it("raises a ground strip by its surface, so the walking edge stays GROUND_LIFT_M up", () => {
    const { at, feet } = street();
    const strips = at(DEPTH.ground).filter(({ key }) => key === `side:${manifest.streets.high_street.ground}`);
    expect(strips.length).toBeGreaterThan(0);
    for (const { y } of strips) expect(y).toBeCloseTo(feet - (GROUND_LIFT_M + 0.2) * PPM);
  });

  it("frames the paintings with the manifest's moulding", () => {
    const { drawn } = street('banyan_row');
    const frames = drawn.filter(({ key }) => key === 'side:furniture/picture_frame').map(({ args }) => args.slice(4, 8));
    expect(frames.length).toBeGreaterThan(0);
    for (const sides of frames) expect(sides).toEqual([20, 21, 22, 23]);
  });
});
