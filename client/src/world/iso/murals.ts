import { server, type Position, type Wall } from '../../net';
import type { Point } from '../view';
import { PAIR_DEPTH } from './crossfade';
import { imageOrigin } from './depth';
import { tintColour, type Rgb } from './lighting';
import type { IsoTile, SceneryObject } from './manifest';
import { feetOf, project } from './projection';

/** `STOREY_M` in server/simile/art/iso/town.py. */
export const STOREY_METRES = 3;

/** Above both of its building's crossfading images, and below `RESIDENT_TIE`. */
export const MURAL_DEPTH = 3 * PAIR_DEPTH;

export const MURAL_FADE_SECONDS = 1.5;

export const MURAL_REACH_TILES = 3;

/** A wall's face on screen: its top-left corner, and its top and left edges from there. */
export type Quad = { origin: Point; across: Point; down: Point };

export type Box = { x: number; y: number; width: number; height: number };

export type Transform = [a: number, b: number, c: number, d: number, e: number, f: number];

/** A crop of the mural's box from `cropX`, and the ground in front of its left and right edges. */
export type MuralSlice = {
  cropX: number;
  cropWidth: number;
  depth: number;
  feet: [left: Point, right: Point];
};

/** The face's two ends on the ground, the one on the left of the screen first. */
function faceEnds({ x, y, width, face }: Wall): [Point, Point] {
  return face === 'south'
    ? [
        { x, y: y + 1 },
        { x: x + width, y: y + 1 },
      ]
    : [
        { x: x + 1, y: y + width },
        { x: x + 1, y },
      ];
}

export function wallQuad(wall: Wall, tile: IsoTile): Quad {
  const [left, right] = faceEnds(wall);
  const [top, bottom] = [wall.top * STOREY_METRES, wall.bottom * STOREY_METRES];
  const origin = project(tile, left, top);
  const end = project(tile, right, top);
  const foot = project(tile, left, bottom);
  return {
    origin,
    across: { x: end.x - origin.x, y: end.y - origin.y },
    down: { x: foot.x - origin.x, y: foot.y - origin.y },
  };
}

/** The whole-pixel box around a quad. */
export function quadBox({ origin, across, down }: Quad): Box {
  const xs = [0, across.x, down.x, across.x + down.x].map((dx) => origin.x + dx);
  const ys = [0, across.y, down.y, across.y + down.y].map((dy) => origin.y + dy);
  const [x, y] = [Math.floor(Math.min(...xs)), Math.floor(Math.min(...ys))];
  return { x, y, width: Math.ceil(Math.max(...xs)) - x, height: Math.ceil(Math.max(...ys)) - y };
}

/** Takes an image's pixels onto the quad, in its box: a canvas `setTransform`. */
export function imageTransform(quad: Quad, box: Box, width: number, height: number): Transform {
  const { origin, across, down } = quad;
  return [
    across.x / width,
    across.y / width,
    down.x / height,
    down.y / height,
    origin.x - box.x,
    origin.y - box.y,
  ];
}

export function inQuad({ origin, across, down }: Quad, point: Point): boolean {
  const det = across.x * down.y - across.y * down.x;
  if (det === 0) return false;
  const [px, py] = [point.x - origin.x, point.y - origin.y];
  const s = (px * down.y - py * down.x) / det;
  const t = (py * across.x - px * across.y) / det;
  return s >= 0 && s <= 1 && t >= 0 && t <= 1;
}

/** The building whose south row or east column the wall is on, with the face on its edge. */
export function buildingOf(
  wall: Wall,
  objects: readonly SceneryObject[],
): SceneryObject | undefined {
  return objects.find(({ kind, footprint: [x0, y0, x1, y1] }) => {
    if (kind !== 'building' || wall.x < x0 || wall.y < y0) return false;
    return wall.face === 'south'
      ? wall.y + 1 === y1 && wall.x + wall.width <= x1
      : wall.x + 1 === x1 && wall.y + wall.width <= y1;
  });
}

/** The point on the ground half a tile in front of the face, below screen x. */
export function inFront(wall: Wall, screenX: number, tile: IsoTile): Point {
  const along = screenX / (tile.width / 2);
  const clamp = (value: number) => Math.min(Math.max(value, 0), wall.width);
  if (wall.face === 'south') {
    const y = wall.y + 1;
    return { x: wall.x + clamp(along + y - wall.x), y: y + 0.5 };
  }
  const x = wall.x + 1;
  return { x: x + 0.5, y: wall.y + clamp(x - along - wall.y) };
}

/** The mural cut where its building's slices are, each just in front of the slice it's on. */
export function muralSlices(
  wall: Wall,
  building: SceneryObject,
  box: Box,
  tile: IsoTile,
): MuralSlice[] {
  const left = imageOrigin(building, tile).x;
  return building.slices.flatMap((slice) => {
    const start = Math.max(left + slice.x, box.x);
    const end = Math.min(left + slice.x + slice.width, box.x + box.width);
    if (end <= start) return [];
    return [
      {
        cropX: start - box.x,
        cropWidth: end - start,
        depth: slice.depth + MURAL_DEPTH,
        feet: [inFront(wall, start, tile), inFront(wall, end, tile)],
      },
    ];
  });
}

/** How far the feet are from the face, or `undefined` behind it. */
function distanceInFront(wall: Wall, feet: Point): number | undefined {
  const [out, along, start] =
    wall.face === 'south'
      ? [feet.y - (wall.y + 1), feet.x, wall.x]
      : [feet.x - (wall.x + 1), feet.y, wall.y];
  if (out <= 0) return undefined;
  return Math.hypot(out, Math.max(start - along, 0, along - (start + wall.width)));
}

/** The painted wall nearest the player, if they stand in front of it within reach. */
export function wallNear(walls: readonly Wall[], position: Position | undefined): Wall | undefined {
  if (!position) return undefined;
  const feet = feetOf(position);
  let nearest: { wall: Wall; distance: number } | undefined;
  for (const wall of walls) {
    const distance = wall.mural ? distanceInFront(wall, feet) : undefined;
    if (distance === undefined || distance > MURAL_REACH_TILES) continue;
    if (!nearest || distance < nearest.distance) nearest = { wall, distance };
  }
  return nearest?.wall;
}

/** The outgoing mural under the incoming one at `fade`, together as see-through as `alpha`. */
export function fadeAlphas(
  fade: number,
  alpha = 1,
  incoming = true,
): [outgoing: number, incoming: number] {
  if (!incoming) return [alpha * (1 - fade), 0];
  const over = alpha * fade;
  return [over === 1 ? 0 : (alpha - over) / (1 - over), over];
}

type Server = Pick<typeof server, 'on'>;

/** The walls from the latest `murals` message, kept from startup since it comes on connect. */
export class MuralWalls {
  walls: Wall[] = [];
  private readonly listeners = new Set<(walls: Wall[]) => void>();

  constructor(server: Server) {
    server.on('murals', ({ walls }) => {
      this.walls = walls;
      for (const listener of this.listeners) listener(walls);
    });
  }

  wall(id: string): Wall | undefined {
    return this.walls.find((wall) => wall.id === id);
  }

  onChange(listener: (walls: Wall[]) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }
}

export const muralWalls = new MuralWalls(server);

/** What the mural panel needs from the scene drawing the murals: only the iso one does. */
export interface MuralView {
  /** The wall whose mural is at a point on the game canvas. */
  wallAt(point: Point): string | undefined;
}

let registered: MuralView | undefined;

export function setMuralView(view: MuralView): () => void {
  registered = view;
  return () => {
    if (registered === view) registered = undefined;
  };
}

export const muralView = (): MuralView | undefined => registered;

/** The part of a Phaser image the murals use. */
export type MuralImage = {
  setCrop(x: number, y: number, width: number, height: number): unknown;
  setDepth(depth: number): unknown;
  setAlpha(alpha: number): unknown;
  setTint(topLeft: number, topRight: number, bottomLeft: number, bottomRight: number): unknown;
  destroy(): void;
};

export type Picture = { width: number; height: number; close?(): void };

/** How the murals reach the scene: Phaser in the game, a fake in tests. */
export type MuralStage<P extends Picture = Picture> = {
  load(url: string): Promise<P>;
  /** Adds the picture as a texture, drawn into the box through the transform. */
  paint(key: string, picture: P, box: Box, transform: Transform): void;
  unpaint(key: string): void;
  /** An image of the texture with its top-left at (x, y). */
  image(key: string, x: number, y: number): MuralImage;
};

type Painting = { key: string; images: MuralImage[] };

type Painted = {
  wall: Wall;
  building: string;
  quad: Quad;
  box: Box;
  slices: MuralSlice[];
  workId?: string;
  shown?: Painting;
  leaving?: Painting;
  fade: number;
};

/** Each wall's mural on its face, lit, cut away and sorted with its building. */
export class IsoMurals<P extends Picture = Picture> {
  private readonly painted = new Map<string, Painted>();
  private readonly objects: readonly SceneryObject[];
  private readonly tile: IsoTile;
  private readonly stage: MuralStage<P>;
  private readonly stop: () => void;
  private textures = 0;

  constructor(
    walls: MuralWalls,
    objects: readonly SceneryObject[],
    tile: IsoTile,
    stage: MuralStage<P>,
  ) {
    this.objects = objects;
    this.tile = tile;
    this.stage = stage;
    this.show(walls.walls, true);
    this.stop = walls.onChange((changed) => this.show(changed, false));
  }

  /** Moves each fade on, and lights and fades every mural like the scenery around it. */
  draw(dt: number, light: (feet: Point) => Rgb, alphaOf: (building: string) => number): void {
    for (const wall of this.painted.values()) {
      wall.fade = Math.min(wall.fade + dt / MURAL_FADE_SECONDS, 1);
      if (wall.fade === 1 && wall.leaving) wall.leaving = this.remove(wall.leaving);
      const [outgoing, incoming] = fadeAlphas(wall.fade, alphaOf(wall.building), !!wall.shown);
      const tints = wall.slices.map(({ feet }) => feet.map((at) => tintColour(light(at))));
      const apply = (painting: Painting | undefined, alpha: number) =>
        painting?.images.forEach((image, i) => {
          const [left, right] = tints[i];
          image.setAlpha(alpha);
          image.setTint(left, right, left, right);
        });
      apply(wall.leaving, outgoing);
      apply(wall.shown, incoming);
    }
  }

  wallAt(point: Point): string | undefined {
    for (const [id, { quad, shown }] of this.painted) if (shown && inQuad(quad, point)) return id;
    return undefined;
  }

  destroy(): void {
    this.stop();
    for (const wall of this.painted.values()) {
      this.remove(wall.shown);
      this.remove(wall.leaving);
    }
    this.painted.clear();
  }

  private show(walls: readonly Wall[], instant: boolean): void {
    const ids = new Set(walls.map(({ id }) => id));
    for (const [id, wall] of this.painted) {
      if (ids.has(id)) continue;
      this.remove(wall.shown);
      this.remove(wall.leaving);
      this.painted.delete(id);
    }
    for (const wall of walls) {
      const painted = this.painted.get(wall.id) ?? this.add(wall);
      if (!painted) continue;
      painted.wall = wall;
      const workId = wall.mural?.work_id;
      if (workId === painted.workId) continue;
      painted.workId = workId;
      if (!wall.mural) {
        this.retire(painted);
        continue;
      }
      this.stage.load(wall.mural.image).then(
        (picture) => this.paint(painted, workId!, picture, instant),
        (error: unknown) => console.error(`Couldn't load the mural on ${wall.id}`, error),
      );
    }
  }

  private add(wall: Wall): Painted | undefined {
    const building = buildingOf(wall, this.objects);
    if (!building) {
      console.warn(`No building has the wall ${wall.id}`);
      return undefined;
    }
    const quad = wallQuad(wall, this.tile);
    const box = quadBox(quad);
    const painted = {
      wall,
      building: building.id,
      quad,
      box,
      slices: muralSlices(wall, building, box, this.tile),
      fade: 1,
    };
    this.painted.set(wall.id, painted);
    return painted;
  }

  private paint(painted: Painted, workId: string, picture: P, instant: boolean): void {
    if (painted.workId !== workId || this.painted.get(painted.wall.id) !== painted) {
      picture.close?.();
      return;
    }
    const { box, slices } = painted;
    const key = `mural/${this.textures++}`;
    const transform = imageTransform(painted.quad, box, picture.width, picture.height);
    this.stage.paint(key, picture, box, transform);
    picture.close?.();
    const images = slices.map(({ cropX, cropWidth, depth }) => {
      const image = this.stage.image(key, box.x, box.y);
      image.setCrop(cropX, 0, cropWidth, box.height);
      image.setDepth(depth + PAIR_DEPTH);
      image.setAlpha(0);
      return image;
    });
    this.retire(painted);
    painted.shown = { key, images };
    painted.fade = instant ? 1 : 0;
  }

  /** The shown mural goes under, to fade out. */
  private retire(painted: Painted): void {
    if (!painted.shown) return;
    this.remove(painted.leaving);
    painted.leaving = painted.shown;
    painted.shown = undefined;
    painted.fade = 0;
    painted.leaving.images.forEach((image, i) => image.setDepth(painted.slices[i].depth));
  }

  private remove(painting: Painting | undefined): undefined {
    if (!painting) return undefined;
    for (const image of painting.images) image.destroy();
    this.stage.unpaint(painting.key);
    return undefined;
  }
}

/** A picture drawn onto its quad, in its box, for `MuralStage.paint`. */
export function skewed(
  picture: CanvasImageSource,
  box: Box,
  transform: Transform,
): HTMLCanvasElement {
  const canvas = document.createElement('canvas');
  [canvas.width, canvas.height] = [box.width, box.height];
  const context = canvas.getContext('2d')!;
  context.imageSmoothingQuality = 'high';
  context.setTransform(...transform);
  context.drawImage(picture, 0, 0);
  return canvas;
}
