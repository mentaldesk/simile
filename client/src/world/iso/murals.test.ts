import { afterEach, describe, expect, it, vi } from 'vitest';
import townPy from '../../../../server/simile/art/iso/town.py?raw';
import { server, type Face, type Mural, type Wall } from '../../net';
import { village } from '../assets';
import type { Point } from '../view';
import { PAIR_DEPTH } from './crossfade';
import { residentDepth } from './depth';
import type { Rgb } from './lighting';
import type { IsoTile, SceneryManifest } from './manifest';
import {
  buildingOf,
  fadeAlphas,
  imageTransform,
  inFront,
  inQuad,
  IsoMurals,
  MURAL_DEPTH,
  MURAL_FADE_SECONDS,
  MURAL_REACH_TILES,
  muralSlices,
  MuralWalls,
  quadBox,
  STOREY_METRES,
  wallNear,
  wallQuad,
  type Box,
  type MuralImage,
  type MuralStage,
  type Picture,
  type Quad,
  type Transform,
} from './murals';
import { feetOf } from './projection';

const { afternoon } = Object.fromEntries(
  Object.values(
    import.meta.glob<SceneryManifest>('../../../../content/art/iso/scenery/*.json', {
      eager: true,
      import: 'default',
    }),
  ).map((manifest) => [manifest.set, manifest]),
);
const TILE: IsoTile = afternoon.tile;

const mural = (workId: string): Mural => ({
  work_id: workId,
  title: `Title of ${workId}`,
  artist: { id: 'kofi', name: 'Kofi Mensah' },
  statement: 'About it.',
  image: `/api/works/${workId}.png`,
});

/** The map's walls, as the server sends them: `content/map/README.md`. */
const WALLS: Wall[] = village.layers
  .find(({ name }) => name === 'murals')!
  .objects!.map(({ name, x = 0, y = 0, width = 0, height = 0, properties = [] }) => {
    const property = (key: string) => properties.find((p) => p.name === key)!.value;
    const face = property('face') as Face;
    const tiles = (px: number) => px / village.tilewidth;
    return {
      id: name,
      x: tiles(x),
      y: tiles(y),
      width: tiles(face === 'south' ? width : height),
      face,
      bottom: property('bottom') as number,
      top: property('top') as number,
      mural: null,
    };
  });
const wallOf = (id: string) => WALLS.find((wall) => wall.id === id)!;
const [CORNER_SHOP, DAILY_GRIND] = [wallOf('corner_shop'), wallOf('daily_grind')];

const painted = (wall: Wall, workId: string): Wall => ({ ...wall, mural: mural(workId) });

const middleOf = ({ origin, across, down }: Quad): Point => ({
  x: origin.x + across.x / 2 + down.x / 2,
  y: origin.y + across.y / 2 + down.y / 2,
});

const apply = ([a, b, c, d, e, f]: Transform, { x, y }: Point, box: Box): Point => ({
  x: box.x + a * x + c * y + e,
  y: box.y + b * x + d * y + f,
});

describe('wallQuad', () => {
  const metres = (storeys: number) => storeys * STOREY_METRES * TILE.px_per_metre_up;

  it('stands a south face on the south edge of its tiles, running east', () => {
    const quad = wallQuad(DAILY_GRIND, TILE);

    expect(quad.origin.x).toBe((28 - 11) * 48);
    expect(quad.origin.y).toBeCloseTo((28 + 11) * 24 - metres(1.9));
    expect(quad.across).toEqual({ x: 3 * 48, y: 3 * 24 });
    expect(quad.down.x).toBe(0);
    expect(quad.down.y).toBeCloseTo(metres(1.9 - 1.05));
  });

  it('stands an east face on the east edge of its tiles, its south end on the left', () => {
    const quad = wallQuad(CORNER_SHOP, TILE);

    expect(quad.origin.x).toBe((22 - 10) * 48);
    expect(quad.origin.y).toBeCloseTo((22 + 10) * 24 - metres(2.85));
    expect(quad.across).toEqual({ x: 4 * 48, y: -4 * 24 });
    expect(quad.down.x).toBe(0);
    expect(quad.down.y).toBeCloseTo(metres(2.85 - 0.7));
  });

  it('takes a storey from town.py', () => {
    expect(townPy).toMatch(new RegExp(`^STOREY_M = ${STOREY_METRES.toFixed(1)}$`, 'm'));
  });

  it.each(WALLS)('draws the image onto $id corner to corner, inside its box', (wall) => {
    const quad = wallQuad(wall, TILE);
    const box = quadBox(quad);
    const transform = imageTransform(quad, box, 320, 200);
    const corner = (s: number, t: number) => ({
      x: quad.origin.x + s * quad.across.x + t * quad.down.x,
      y: quad.origin.y + s * quad.across.y + t * quad.down.y,
    });

    for (const [s, t] of [
      [0, 0],
      [1, 0],
      [0, 1],
      [1, 1],
    ]) {
      const drawn = apply(transform, { x: s * 320, y: t * 200 }, box);
      expect(drawn.x).toBeCloseTo(corner(s, t).x);
      expect(drawn.y).toBeCloseTo(corner(s, t).y);
      expect(drawn.x).toBeGreaterThanOrEqual(box.x);
      expect(drawn.x).toBeLessThanOrEqual(box.x + box.width);
      expect(drawn.y).toBeGreaterThanOrEqual(box.y);
      expect(drawn.y).toBeLessThanOrEqual(box.y + box.height);
    }
    expect(Object.values(box).every(Number.isInteger)).toBe(true);
  });

  it('hit-tests the face, not its box', () => {
    const quad = wallQuad(DAILY_GRIND, TILE);
    const box = quadBox(quad);
    const middle = middleOf(quad);

    expect(inQuad(quad, middle)).toBe(true);
    expect(inQuad(quad, { x: box.x + box.width - 1, y: box.y + 1 })).toBe(false);
    expect(inQuad(quad, { x: box.x + 1, y: box.y + box.height - 1 })).toBe(false);
  });
});

describe('depth', () => {
  it('reads the walls the map has', () => {
    expect(WALLS.map(({ id }) => id).sort()).toEqual(
      ['banyan_row', 'corner_shop', 'daily_grind', 'garden_flats', 'tower'],
    );
    expect(DAILY_GRIND).toMatchObject({ x: 28, y: 10, width: 3, face: 'south' });
    expect(CORNER_SHOP).toMatchObject({ x: 21, y: 6, width: 4, face: 'east' });
  });

  it.each([
    ['corner_shop', 'building-13-6'],
    ['daily_grind', 'building-28-6'],
    ['tower', 'building-57-4'],
    ['garden_flats', 'building-29-28'],
    ['banyan_row', 'building-14-29'],
  ])('finds the building %s is on', (id, building) => {
    expect(buildingOf(wallOf(id), afternoon.objects)?.id).toBe(building);
  });

  it('finds no building for a wall off any face the camera sees', () => {
    expect(buildingOf({ ...DAILY_GRIND, y: 9 }, afternoon.objects)).toBeUndefined();
    expect(buildingOf({ ...CORNER_SHOP, x: 20 }, afternoon.objects)).toBeUndefined();
    expect(buildingOf({ ...DAILY_GRIND, width: 9 }, afternoon.objects)).toBeUndefined();
  });

  it.each(WALLS)('cuts $id across its building slices, without gaps', (wall) => {
    const building = buildingOf(wall, afternoon.objects)!;
    const box = quadBox(wallQuad(wall, TILE));
    const slices = muralSlices(wall, building, box, TILE);

    expect(slices[0].cropX).toBe(0);
    slices.slice(1).forEach((slice, i) => {
      expect(slice.cropX).toBe(slices[i].cropX + slices[i].cropWidth);
    });
    expect(slices.at(-1)!.cropX + slices.at(-1)!.cropWidth).toBe(box.width);
    const depths = new Set(building.slices.map(({ depth }) => depth + MURAL_DEPTH));
    expect(slices.every(({ depth }) => depths.has(depth))).toBe(true);
  });

  it.each(WALLS)(
    'sorts $id above its building and below anyone in front of it, or anyone behind it',
    (wall) => {
      const building = buildingOf(wall, afternoon.objects)!;
      const box = quadBox(wallQuad(wall, TILE));
      const [x0, y0] = building.footprint;
      const behind = residentDepth(feetOf({ x: x0, y: y0 - 1 }), TILE);

      for (const { depth, feet } of muralSlices(wall, building, box, TILE)) {
        const under = depth - MURAL_DEPTH;
        expect(depth).toBeGreaterThan(under + PAIR_DEPTH);
        for (const at of feet) expect(residentDepth(at, TILE)).toBeGreaterThan(depth + PAIR_DEPTH);
        expect(behind).toBeLessThan(under);
      }
    },
  );

  it('lights each slice from the ground in front of it', () => {
    expect(inFront(DAILY_GRIND, (29.5 - 11) * 48, TILE)).toEqual({ x: 29.5, y: 11.5 });
    expect(inFront(DAILY_GRIND, -1e4, TILE)).toEqual({ x: 28, y: 11.5 });
    expect(inFront(CORNER_SHOP, (22 - 8) * 48, TILE)).toEqual({ x: 22.5, y: 8 });
    expect(inFront(CORNER_SHOP, 1e4, TILE)).toEqual({ x: 22.5, y: 6 });
  });
});

describe('wallNear', () => {
  const grind = painted(DAILY_GRIND, 'mars');
  const shop = painted(CORNER_SHOP, 'river');

  it('finds a painted wall the player stands in front of, within reach', () => {
    expect(wallNear([grind, shop], { x: 29, y: 11 })).toBe(grind);
    expect(wallNear([grind, shop], { x: 29, y: 10.5 + MURAL_REACH_TILES })).toBe(grind);
    expect(wallNear([grind, shop], { x: 22, y: 8 })).toBe(shop);
  });

  it('finds none out of reach, beside the wall or behind it', () => {
    expect(wallNear([grind], { x: 29, y: 11 + MURAL_REACH_TILES })).toBeUndefined();
    expect(wallNear([grind], { x: 34, y: 11 })).toBeUndefined();
    expect(wallNear([grind], { x: 29, y: 5 })).toBeUndefined();
    expect(wallNear([grind], undefined)).toBeUndefined();
  });

  it('finds none on a blank wall', () => {
    expect(wallNear([DAILY_GRIND], { x: 29, y: 11 })).toBeUndefined();
  });

  it('finds the nearest of two', () => {
    const next = painted({ ...DAILY_GRIND, id: 'next', x: 32 }, 'next');
    expect(wallNear([grind, next], { x: 31.4, y: 11 })).toBe(next);
  });
});

describe('fadeAlphas', () => {
  it('keeps the outgoing opaque under the incoming', () => {
    expect(fadeAlphas(0)).toEqual([1, 0]);
    expect(fadeAlphas(0.4)).toEqual([1, 0.4]);
    expect(fadeAlphas(1)).toEqual([0, 1]);
  });

  it('fades both together as one would be when cut away', () => {
    const [outgoing, incoming] = fadeAlphas(0.5, 0.3);
    expect(incoming + outgoing * (1 - incoming)).toBeCloseTo(0.3);
    expect(fadeAlphas(1, 0.3)).toEqual([0, 0.3]);
  });

  it('fades the outgoing out when nothing comes in', () => {
    expect(fadeAlphas(0.25, 1, false)).toEqual([0.75, 0]);
    expect(fadeAlphas(0.5, 0.3, false)).toEqual([0.15, 0]);
  });
});

describe('MuralWalls', () => {
  it('keeps the latest walls and tells listeners', () => {
    const walls = new MuralWalls(server);
    const heard = vi.fn();
    const stop = walls.onChange(heard);

    server.dispatch(JSON.stringify({ type: 'murals', walls: [painted(DAILY_GRIND, 'mars')] }));

    expect(walls.wall('daily_grind')?.mural?.title).toBe('Title of mars');
    expect(heard).toHaveBeenCalledWith(walls.walls);
    stop();
    server.dispatch(JSON.stringify({ type: 'murals', walls: [] }));
    expect(walls.walls).toEqual([]);
    expect(heard).toHaveBeenCalledTimes(1);
  });
});

type FakeImage = MuralImage & {
  key: string;
  at: Point;
  crop?: Box;
  depth: number;
  alpha: number;
  tint: number[];
  destroyed: boolean;
};

class FakeStage implements MuralStage {
  readonly images: FakeImage[] = [];
  readonly textures = new Map<string, { picture: Picture; box: Box; transform: Transform }>();
  readonly loads: string[] = [];
  readonly pictures = new Map<string, Picture & { close: () => void }>();
  private readonly pending = new Map<string, (picture: Picture) => void>();
  hold = false;

  load(url: string): Promise<Picture> {
    this.loads.push(url);
    const picture = { width: 300, height: 200, close: vi.fn() };
    this.pictures.set(url, picture);
    if (!this.hold) return Promise.resolve(picture);
    return new Promise((resolve) => this.pending.set(url, () => resolve(picture)));
  }

  release(url: string): void {
    this.pending.get(url)?.(this.pictures.get(url)!);
  }

  paint(key: string, picture: Picture, box: Box, transform: Transform): void {
    this.textures.set(key, { picture, box, transform });
  }

  unpaint(key: string): void {
    this.textures.delete(key);
  }

  image(key: string, x: number, y: number): MuralImage {
    const image: FakeImage = {
      key,
      at: { x, y },
      depth: 0,
      alpha: 1,
      tint: [],
      destroyed: false,
      setCrop: (cx, cy, width, height) => (image.crop = { x: cx, y: cy, width, height }),
      setDepth: (depth) => (image.depth = depth),
      setAlpha: (alpha) => (image.alpha = alpha),
      setTint: (...tint) => (image.tint = tint),
      destroy: () => (image.destroyed = true),
    };
    this.images.push(image);
    return image;
  }

  live(url?: string): FakeImage[] {
    const picture = url && this.pictures.get(url);
    const key = [...this.textures].find(([, texture]) => texture.picture === picture)?.[0];
    return this.images.filter((image) => !image.destroyed && (!url || image.key === key));
  }
}

describe('IsoMurals', () => {
  const flush = () => new Promise((resolve) => setTimeout(resolve));
  const white = (): Rgb => [1, 1, 1];
  const opaque = () => 1;
  let murals: IsoMurals | undefined;

  afterEach(() => {
    murals?.destroy();
    murals = undefined;
    vi.restoreAllMocks();
  });

  function start(walls: Wall[]): { stage: FakeStage; store: MuralWalls } {
    const store = new MuralWalls(server);
    store.walls = walls;
    const stage = new FakeStage();
    murals = new IsoMurals(store, afternoon.objects, TILE, stage);
    return { stage, store };
  }

  const send = (walls: Wall[]) => server.dispatch(JSON.stringify({ type: 'murals', walls }));

  it('paints each mural into its box, a crop per slice just in front of its building', async () => {
    const { stage } = start([painted(DAILY_GRIND, 'mars'), CORNER_SHOP]);
    await flush();
    murals!.draw(0, white, opaque);

    expect(stage.loads).toEqual(['/api/works/mars.png']);
    const quad = wallQuad(DAILY_GRIND, TILE);
    const box = quadBox(quad);
    const [texture] = stage.textures.values();
    expect(texture.box).toEqual(box);
    expect(texture.transform).toEqual(imageTransform(quad, box, 300, 200));
    expect(stage.pictures.get('/api/works/mars.png')!.close).toHaveBeenCalled();

    const building = buildingOf(DAILY_GRIND, afternoon.objects)!;
    const slices = muralSlices(DAILY_GRIND, building, box, TILE);
    const images = stage.live();
    expect(images).toHaveLength(slices.length);
    images.forEach((image, i) => {
      expect(image.at).toEqual({ x: box.x, y: box.y });
      const { cropX, cropWidth } = slices[i];
      expect(image.crop).toEqual({ x: cropX, y: 0, width: cropWidth, height: box.height });
      expect(image.depth).toBe(slices[i].depth + PAIR_DEPTH);
      expect(image.alpha).toBe(1);
    });
  });

  it('lights the mural from the ground in front, without a step between slices', async () => {
    const { stage } = start([painted(DAILY_GRIND, 'mars')]);
    await flush();
    const lit: Point[] = [];
    const light = (feet: Point): Rgb => {
      lit.push(feet);
      return [1, (feet.x - 28) / 3, 0];
    };
    murals!.draw(0, light, opaque);

    const images = stage.live();
    expect(lit.every(({ y }) => y === 11.5)).toBe(true);
    expect(images[0].tint[0]).toBe(0xff0000);
    expect(images.at(-1)!.tint[1]).toBe(0xffff00);
    images.forEach(({ tint: [left, right, bottomLeft, bottomRight] }, i) => {
      expect([bottomLeft, bottomRight]).toEqual([left, right]);
      if (i > 0) expect(left).toBe(images[i - 1].tint[1]);
    });
  });

  it('cuts the mural away with its building', async () => {
    const { stage } = start([painted(DAILY_GRIND, 'mars'), painted(CORNER_SHOP, 'river')]);
    await flush();
    murals!.draw(0, white, (building) => (building === 'building-28-6' ? 0.3 : 1));

    expect(stage.live('/api/works/mars.png').every(({ alpha }) => alpha === 0.3)).toBe(true);
    expect(stage.live('/api/works/river.png').every(({ alpha }) => alpha === 1)).toBe(true);
  });

  it('fades a new mural in over the old one, then drops the old one', async () => {
    const { stage } = start([painted(DAILY_GRIND, 'mars')]);
    await flush();
    send([painted(DAILY_GRIND, 'river')]);
    await flush();
    const [old, fresh] = [stage.live('/api/works/mars.png'), stage.live('/api/works/river.png')];

    murals!.draw(MURAL_FADE_SECONDS / 2, white, opaque);
    expect(old.every(({ alpha }) => alpha === 1)).toBe(true);
    expect(fresh.every(({ alpha }) => alpha === 0.5)).toBe(true);
    expect(fresh[0].depth).toBeGreaterThan(old[0].depth);

    murals!.draw(MURAL_FADE_SECONDS / 2, white, opaque);
    expect(old.every(({ destroyed }) => destroyed)).toBe(true);
    expect(fresh.every(({ alpha }) => alpha === 1)).toBe(true);
    expect(stage.textures.size).toBe(1);
  });

  it('fades a mural out when its wall goes blank', async () => {
    const { stage } = start([painted(DAILY_GRIND, 'mars')]);
    await flush();
    send([DAILY_GRIND]);
    const images = stage.live();

    murals!.draw(MURAL_FADE_SECONDS / 4, white, opaque);
    expect(images.every(({ alpha }) => alpha === 0.75)).toBe(true);
    expect(murals!.wallAt(wallQuad(DAILY_GRIND, TILE).origin)).toBeUndefined();

    murals!.draw(MURAL_FADE_SECONDS, white, opaque);
    expect(images.every(({ destroyed }) => destroyed)).toBe(true);
    expect(stage.textures.size).toBe(0);
  });

  it('fades in a mural painted on a blank wall', async () => {
    const { stage } = start([DAILY_GRIND]);
    send([painted(DAILY_GRIND, 'mars')]);
    await flush();

    murals!.draw(0, white, opaque);
    expect(stage.live().every(({ alpha }) => alpha === 0)).toBe(true);
  });

  it('drops an image that loads after its wall has moved on', async () => {
    const { stage } = start([]);
    stage.hold = true;
    send([painted(DAILY_GRIND, 'mars')]);
    send([painted(DAILY_GRIND, 'river')]);
    stage.release('/api/works/river.png');
    stage.release('/api/works/mars.png');
    await flush();

    expect([...stage.textures.values()].map(({ picture }) => picture)).toEqual([
      stage.pictures.get('/api/works/river.png'),
    ]);
    expect(stage.pictures.get('/api/works/mars.png')!.close).toHaveBeenCalled();
  });

  it('says which mural is at a point', async () => {
    start([painted(DAILY_GRIND, 'mars'), CORNER_SHOP]);
    await flush();
    const quad = wallQuad(DAILY_GRIND, TILE);
    const middle = middleOf(quad);

    expect(murals!.wallAt(middle)).toBe('daily_grind');
    expect(murals!.wallAt({ x: middle.x, y: middle.y - quad.down.y })).toBeUndefined();
    expect(murals!.wallAt(wallQuad(CORNER_SHOP, TILE).origin)).toBeUndefined();
  });

  it('skips a wall on no building', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const { stage } = start([painted({ ...DAILY_GRIND, y: 9 }, 'mars')]);
    await flush();

    expect(warn).toHaveBeenCalledWith('No building has the wall daily_grind');
    expect(stage.loads).toEqual([]);
  });

  it('takes every mural down, and stops listening, when destroyed', async () => {
    const { stage } = start([painted(DAILY_GRIND, 'mars')]);
    await flush();
    murals!.destroy();
    send([painted(DAILY_GRIND, 'river')]);
    await flush();

    expect(stage.live()).toEqual([]);
    expect(stage.textures.size).toBe(0);
    expect(stage.loads).toEqual(['/api/works/mars.png']);
  });

  it('takes a wall down when the server stops sending it', async () => {
    const { stage } = start([painted(DAILY_GRIND, 'mars')]);
    await flush();
    send([]);

    expect(stage.live()).toEqual([]);
  });
});
