import { server, type Frame } from '../../net';
import type { Point } from '../view';
import { PAIR_DEPTH } from './crossfade';
import { imageOrigin } from './depth';
import { tintColour, type Rgb } from './lighting';
import type { IsoTile, SceneryManifest, SceneryObject } from './manifest';
import {
  fadeAlphas,
  imageTransform,
  MURAL_FADE_SECONDS,
  quadBox,
  type Box,
  type MuralImage,
  type MuralStage,
  type Picture,
  type Quad,
} from './murals';

/** Just under its frame's slices, so the moulding covers the painting's edges. */
export const UNDER_FRAME = PAIR_DEPTH / 2;

type Server = Pick<typeof server, 'on'>;

/** The frames from the latest `paintings` message, kept from startup since it comes on connect. */
export class GalleryFrames {
  frames: Frame[] = [];
  private readonly listeners = new Set<(frames: Frame[]) => void>();

  constructor(server: Server) {
    server.on('paintings', ({ frames }) => {
      this.frames = frames;
      for (const listener of this.listeners) listener(frames);
    });
  }

  frame(map: string, id: string): Frame | undefined {
    return this.frames.find((frame) => frame.map === map && frame.id === id);
  }

  onChange(listener: (frames: Frame[]) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }
}

export const galleryFrames = new GalleryFrames(server);

export const isFrame = ({ kind, canvas }: SceneryObject): boolean => kind === 'frame' && !!canvas;

/** The frame's opening on screen, from its `canvas` corners in the frame's image. */
export function canvasQuad(frame: SceneryObject, tile: IsoTile): Quad {
  const origin = imageOrigin(frame, tile);
  const [topLeft, topRight, , bottomLeft] = frame.canvas!.map(([x, y]) => ({ x: origin.x + x, y: origin.y + y }));
  return {
    origin: topLeft,
    across: { x: topRight.x - topLeft.x, y: topRight.y - topLeft.y },
    down: { x: bottomLeft.x - topLeft.x, y: bottomLeft.y - topLeft.y },
  };
}

export type CanvasSlice = { cropX: number; cropWidth: number; depth: number };

/** The painting cut where its frame's slices are, each just under the slice it's in. */
export function canvasSlices(frame: SceneryObject, box: Box, tile: IsoTile): CanvasSlice[] {
  const left = imageOrigin(frame, tile).x;
  return frame.slices.flatMap((slice) => {
    const start = Math.max(left + slice.x, box.x);
    const end = Math.min(left + slice.x + slice.width, box.x + box.width);
    if (end <= start) return [];
    return [{ cropX: start - box.x, cropWidth: end - start, depth: slice.depth - UNDER_FRAME }];
  });
}

/** Half a tile in front of the frame's face, on the ground, where its light is read. */
export function frontOf({ footprint: [x0, y0, x1, y1] }: SceneryObject): Point {
  return x1 - x0 >= y1 - y0 ? { x: (x0 + x1) / 2, y: y1 + 0.5 } : { x: x1 + 0.5, y: (y0 + y1) / 2 };
}

/** How the paintings reach the scene: Phaser in the game, a fake in tests. */
export type PaintingStage<P extends Picture = Picture> = Omit<MuralStage<P>, 'sample'>;

type Shown = { key: string; images: MuralImage[] };

type Hanging = {
  frame: SceneryObject;
  quad: Quad;
  box: Box;
  slices: CanvasSlice[];
  front: Point;
  workId?: string;
  shown?: Shown;
  leaving?: Shown;
  fade: number;
};

/** Draws the paintings in one interior's frames, each into its frame's opening. */
export class IsoPaintings<P extends Picture = Picture> {
  readonly map: string;
  private readonly hangings = new Map<string, Hanging>();
  private readonly stage: PaintingStage<P>;
  private readonly stop: () => void;
  private textures = 0;

  constructor(frames: GalleryFrames, manifest: SceneryManifest, stage: PaintingStage<P>) {
    this.map = manifest.map.id ?? '';
    this.stage = stage;
    for (const frame of manifest.objects.filter(isFrame)) {
      const quad = canvasQuad(frame, manifest.tile);
      const box = quadBox(quad);
      const slices = canvasSlices(frame, box, manifest.tile);
      this.hangings.set(frame.id, { frame, quad, box, slices, front: frontOf(frame), fade: 1 });
    }
    this.show(frames.frames, true);
    this.stop = frames.onChange((changed) => this.show(changed, false));
  }

  /** Hidden unless `visible`. `light` tints each painting, and `alphaOf` fades it with its wall. */
  draw(dt: number, visible: boolean, light: (feet: Point) => Rgb, alphaOf: (frame: string) => number): void {
    for (const hanging of this.hangings.values()) {
      hanging.fade = Math.min(hanging.fade + dt / MURAL_FADE_SECONDS, 1);
      if (hanging.fade === 1 && hanging.leaving) hanging.leaving = this.remove(hanging.leaving);
      const alpha = visible ? alphaOf(hanging.frame.id) : 0;
      const [outgoing, incoming] = fadeAlphas(hanging.fade, alpha, !!hanging.shown);
      const tint = tintColour(light(hanging.front));
      const apply = (shown: Shown | undefined, value: number) =>
        shown?.images.forEach((image) => {
          image.setAlpha(value);
          image.setTint(tint, tint, tint, tint);
        });
      apply(hanging.leaving, outgoing);
      apply(hanging.shown, incoming);
    }
  }

  destroy(): void {
    this.stop();
    for (const hanging of this.hangings.values()) {
      this.remove(hanging.shown);
      this.remove(hanging.leaving);
    }
    this.hangings.clear();
  }

  private show(frames: readonly Frame[], instant: boolean): void {
    for (const { id, map, painting } of frames) {
      const hanging = map === this.map ? this.hangings.get(id) : undefined;
      if (!hanging || painting?.work_id === hanging.workId) continue;
      hanging.workId = painting?.work_id;
      if (!painting) {
        this.retire(hanging);
        continue;
      }
      this.stage.load(painting.image).then(
        (picture) => this.paint(hanging, painting.work_id, picture, instant),
        (error: unknown) => console.error(`Couldn't load the painting in ${id}`, error),
      );
    }
  }

  private paint(hanging: Hanging, workId: string, picture: P, instant: boolean): void {
    if (hanging.workId !== workId || this.hangings.get(hanging.frame.id) !== hanging) {
      picture.close?.();
      return;
    }
    const { box, quad, slices } = hanging;
    const key = `painting/${this.textures++}`;
    this.stage.paint(key, picture, box, imageTransform(quad, box, picture.width, picture.height));
    picture.close?.();
    const images = slices.map(({ cropX, cropWidth, depth }) => {
      const image = this.stage.image(key, box.x, box.y);
      image.setCrop(cropX, 0, cropWidth, box.height);
      image.setDepth(depth);
      image.setAlpha(0);
      return image;
    });
    this.retire(hanging);
    hanging.shown = { key, images };
    hanging.fade = instant ? 1 : 0;
  }

  private retire(hanging: Hanging): void {
    if (!hanging.shown) return;
    this.remove(hanging.leaving);
    hanging.leaving = hanging.shown;
    hanging.shown = undefined;
    hanging.fade = 0;
    hanging.leaving.images.forEach((image, i) => image.setDepth(hanging.slices[i].depth - UNDER_FRAME));
  }

  private remove(shown: Shown | undefined): undefined {
    if (!shown) return undefined;
    for (const image of shown.images) image.destroy();
    this.stage.unpaint(shown.key);
    return undefined;
  }
}
