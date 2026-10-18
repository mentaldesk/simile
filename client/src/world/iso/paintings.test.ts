import { describe, expect, it, vi } from 'vitest';
import { server, type Frame, type Painting } from '../../net';
import type { Point } from '../view';
import { imageOrigin } from './depth';
import type { Rgb } from './lighting';
import type { SceneryManifest } from './manifest';
import { MURAL_FADE_SECONDS, type Box, type MuralImage, type Picture, type Transform } from './murals';
import {
  canvasQuad,
  canvasSlices,
  frontOf,
  GalleryFrames,
  IsoPaintings,
  isFrame,
  UNDER_FRAME,
  type PaintingStage,
} from './paintings';

const interiors = import.meta.glob<SceneryManifest>('../../../../content/art/iso/interiors/*.json', {
  eager: true,
  import: 'default',
});
const gallery = Object.values(interiors).find((manifest) => manifest.map.id === 'gallery')!;
const { tile } = gallery;
const frameOf = (id: string) => gallery.objects.find((object) => object.id === id)!;
const FIRST = frameOf('painting_1');
const ON_A_PARTITION = frameOf('painting_9');

const painting = (workId: string): Painting => ({
  work_id: workId,
  title: `Title of ${workId}`,
  artist: { id: 'kofi', name: 'Kofi Mensah' },
  statement: 'About it.',
  image: `/api/gallery/${workId}.png`,
});
const hung = (id: string, workId: string | null, map = 'gallery'): Frame => ({
  id,
  map,
  painting: workId ? painting(workId) : null,
});

describe('frames', () => {
  it('are the 13 painting frames, each with an opening', () => {
    const frames = gallery.objects.filter(isFrame);
    expect(frames.map(({ id }) => id).sort()).toEqual(
      Array.from({ length: 13 }, (_, n) => `painting_${n + 1}`).sort(),
    );
  });

  it('open as wide and tall as the opening the server paints for, 1.34 × 0.84 m', () => {
    const { origin, across, down } = canvasQuad(FIRST, tile);
    const corner = imageOrigin(FIRST, tile);

    expect(origin).toEqual({ x: corner.x + FIRST.canvas![0][0], y: corner.y + FIRST.canvas![0][1] });
    expect((across.x / (tile.width / 2)) * tile.metres).toBeCloseTo(1.34, 1);
    expect(across.y / across.x).toBeCloseTo(tile.height / tile.width);
    expect(down.x).toBeCloseTo(0);
    expect(down.y / tile.px_per_metre_up).toBeCloseTo(0.84, 1);
  });

  it('cut the painting where the frame is sliced, each crop just under its slice', () => {
    const box = { x: 100, y: 50, width: 60, height: 50 };
    const left = imageOrigin(FIRST, tile).x;
    const crops = canvasSlices(FIRST, { ...box, x: left + 8 }, tile);

    const widths = crops.map(({ cropWidth }) => cropWidth);
    expect(widths.reduce((sum, width) => sum + width)).toBe(box.width);
    expect(crops.map(({ depth }) => depth)).toEqual(FIRST.slices.map(({ depth }) => depth - UNDER_FRAME));
    expect(crops[0].cropX).toBe(0);
  });

  it('read their light half a tile in front of their face', () => {
    const [x0, , x1, y1] = FIRST.footprint;
    expect(frontOf(FIRST)).toEqual({ x: (x0 + x1) / 2, y: y1 + 0.5 });
    expect(frontOf({ ...FIRST, footprint: [3, 4, 3.05, 5.4] })).toEqual({ x: 3.55, y: 4.7 });
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

class FakeStage implements PaintingStage {
  readonly images: FakeImage[] = [];
  readonly textures = new Map<string, { picture: Picture; box: Box; transform: Transform }>();
  readonly loads: string[] = [];

  load(url: string): Promise<Picture> {
    this.loads.push(url);
    return Promise.resolve({ width: 960, height: 602, close: vi.fn() });
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

  live(key?: string): FakeImage[] {
    return this.images.filter((image) => !image.destroyed && (!key || image.key === key));
  }
}

const settle = () => new Promise((resolve) => setTimeout(resolve));
const WARM: Rgb = [0.9, 0.8, 0.7];
const light = () => WARM;

function setUp(frames: Frame[]) {
  const listeners = new Set<(message: { frames: Frame[] }) => void>();
  const fakeServer = {
    on: (_type: 'paintings', listener: (message: { frames: Frame[] }) => void) => listeners.add(listener),
  } as unknown as Pick<typeof server, 'on'>;
  const galleryFrames = new GalleryFrames(fakeServer);
  const send = (list: Frame[]) => listeners.forEach((listener) => listener({ frames: list }));
  send(frames);
  const stage = new FakeStage();
  const paintings = new IsoPaintings(galleryFrames, gallery, stage);
  return { galleryFrames, send, stage, paintings };
}

describe('IsoPaintings', () => {
  it('paints each hung painting into its frame, just under the frame', async () => {
    const { stage } = setUp([
      hung('painting_1', 'kofi-1'),
      hung('painting_2', null),
      hung('painting_3', 'x', 'noodle_bar'),
    ]);
    await settle();

    expect(stage.loads).toEqual(['/api/gallery/kofi-1.png']);
    const [[, { box, transform }]] = [...stage.textures];
    const quad = canvasQuad(FIRST, tile);
    const corner = (x: number, y: number) => ({
      x: box.x + transform[0] * x + transform[2] * y + transform[4],
      y: box.y + transform[1] * x + transform[3] * y + transform[5],
    });
    expect(corner(0, 0).x).toBeCloseTo(quad.origin.x);
    expect(corner(960, 602).y).toBeCloseTo(quad.origin.y + quad.across.y + quad.down.y);
    const images = stage.live();
    const depths = canvasSlices(FIRST, box, tile).map(({ depth }) => depth);
    expect(images.map(({ depth }) => depth)).toEqual(depths);
    expect(images.every(({ depth }, i) => depth < FIRST.slices[i].depth)).toBe(true);
  });

  it('shows them only on their map, lit where they hang and faded with their wall', async () => {
    const { stage, paintings } = setUp([hung('painting_1', 'a'), hung('painting_9', 'b')]);
    await settle();
    const lit: Point[] = [];

    const lightAt = (feet: Point) => {
      lit.push(feet);
      return WARM;
    };
    paintings.draw(0.1, true, lightAt, (frame) => (frame === ON_A_PARTITION.id ? 0.3 : 1));

    const [first, partition] = [stage.live('painting/0'), stage.live('painting/1')];
    expect(first.every(({ alpha }) => alpha === 1)).toBe(true);
    expect(partition.every(({ alpha }) => alpha === 0.3)).toBe(true);
    expect(first[0].tint).toEqual(Array(4).fill(0xe6ccb3));
    expect(lit).toContainEqual(frontOf(FIRST));

    paintings.draw(0.1, false, light, () => 1);
    expect(stage.live().every(({ alpha }) => alpha === 0)).toBe(true);
  });

  it('fades a new painting in over the old one, then lets the old one go', async () => {
    const { stage, paintings, send } = setUp([hung('painting_1', 'old')]);
    await settle();
    send([hung('painting_1', 'new')]);
    await settle();

    paintings.draw(MURAL_FADE_SECONDS / 2, true, light, () => 1);
    const [leaving, coming] = [stage.live('painting/0'), stage.live('painting/1')];
    expect(leaving.length).toBeGreaterThan(0);
    expect(coming[0].alpha).toBeCloseTo(0.5);
    expect(leaving[0].depth).toBeLessThan(coming[0].depth);

    paintings.draw(MURAL_FADE_SECONDS, true, light, () => 1);
    expect(stage.textures.has('painting/0')).toBe(false);
    expect(stage.live().every(({ key, alpha }) => key === 'painting/1' && alpha === 1)).toBe(true);
  });

  it('fades out a painting taken down, and unpaints everything when destroyed', async () => {
    const { stage, paintings, send } = setUp([hung('painting_1', 'a'), hung('painting_2', 'b')]);
    await settle();
    send([hung('painting_1', null), hung('painting_2', 'b')]);

    paintings.draw(MURAL_FADE_SECONDS, true, light, () => 1);
    expect(stage.textures.has('painting/0')).toBe(false);

    paintings.destroy();
    expect(stage.textures.size).toBe(0);
    expect(stage.images.every(({ destroyed }) => destroyed)).toBe(true);
  });
});

describe('GalleryFrames', () => {
  it('keeps the latest frames from the server and says when they change', () => {
    const frames = new GalleryFrames(server);
    const heard: Frame[][] = [];
    frames.onChange((changed) => heard.push(changed));

    server.dispatch(JSON.stringify({ type: 'paintings', frames: [hung('painting_1', 'a')] }));

    expect(frames.frame('gallery', 'painting_1')?.painting?.work_id).toBe('a');
    expect(frames.frame('noodle_bar', 'painting_1')).toBeUndefined();
    expect(heard).toHaveLength(1);
  });
});
