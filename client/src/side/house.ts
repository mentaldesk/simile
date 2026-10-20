import Phaser from 'phaser';
import type { Frame } from '../net';
import { DEPTH } from './depths';
import { dropShadow, furnitureKey, tileAlong, type Tints } from './draw';
import {
  dollhouse,
  feetOf,
  furniturePlacement,
  PPM,
  STOREY_M,
  stretchWidth,
  TILE,
  xOf,
  type Dollhouse,
} from './layout';
import type { Placed, SideMap, Village } from './maps';
import { crossing } from './runs';
import type { SceneryManifest } from './scenery';
import type { SideTextures } from './textures';

/** Where on a floor's back wall its windows go, as shares of the building's width. */
const WINDOWS = [0.3, 0.7];
const WINDOW_ROW = 1.9;
const SLAB_M = 0.3;
const FRAME_M = 1.0;
/** The picture frame's moulding in its picture's px, kept as the frame stretches to a painting. */
const MOULDING = { left: 13, right: 11, top: 18, bottom: 14 };
/** How much of its wall a frame may take, and its shape while it's empty. */
const FRAME_FILL = 0.9;
const EMPTY_ASPECT = 0.85;
const LADDER_ABOVE_M = 0.6;
const STAIRS_RAIL_M = 0.9;

type Hung = {
  map: string;
  id: string;
  x: number;
  y: number;
  maxWidth: number;
  frame?: Phaser.GameObjects.NineSlice;
  shadow?: Phaser.GameObjects.Image;
  image?: Phaser.GameObjects.Image;
};

type Car = { image: Phaser.GameObjects.Image; floorLine: number };

/** A building's dollhouse, drawn in place on its street behind its front: each floor's back
 * wall, windows, paintings, furniture, stairs, ladders and lift, and the slabs between them. */
export class House {
  readonly name: string;
  readonly box: Dollhouse;
  private readonly scene: Phaser.Scene;
  private readonly textures: SideTextures;
  private readonly manifest: SceneryManifest;
  private readonly images: Phaser.GameObjects.Image[] = [];
  private readonly cars: Car[] = [];
  private readonly riding: Phaser.GameObjects.Image[] = [];
  /** The floor lines a ride leaves from or arrives at this frame, whose cars are away. */
  private readonly away: number[] = [];
  private readonly frames = new Map<string, Hung>();
  private readonly tints: Tints;
  private shown = true;
  private carKey?: string;

  constructor(
    scene: Phaser.Scene,
    textures: SideTextures,
    manifest: SceneryManifest,
    tints: Tints,
    building: Placed,
    village: Village,
  ) {
    this.scene = scene;
    this.textures = textures;
    this.manifest = manifest;
    this.tints = tints;
    this.name = building.name;
    this.box = dollhouse(building, village.floors(building.name));
    const papers = manifest.buildings[building.name]?.floors ?? [];
    this.box.floors.forEach((floor, n) => this.floor(floor, papers[n], village));
    this.slabs();
    this.setShown(false);
  }

  /** The pictures every floor of every building needs. */
  static pieces(manifest: SceneryManifest, building: string, village: Village): string[] {
    const floors = village.floors(building);
    const furniture = floors.flatMap((map) => map.furniture.map((item) => furnitureKey(manifest, item, map.id)));
    const { platforms } = manifest;
    return [
      ...(manifest.buildings[building]?.floors ?? []),
      ...furniture,
      platforms.stairs,
      platforms.ladder,
      platforms.window,
      platforms.lift,
      platforms.lift_shaft,
      manifest.slab,
      manifest.furniture.picture_frame?.piece,
    ].filter((key): key is string => !!key);
  }

  setShown(shown: boolean): void {
    if (shown === this.shown) return;
    this.shown = shown;
    for (const image of this.images) image.setVisible(shown);
    for (const hung of this.frames.values()) {
      for (const part of [hung.frame, hung.shadow, hung.image]) part?.setVisible(shown);
    }
    if (!shown) for (const image of this.riding) image.setVisible(false);
  }

  /** The car on each floor stays put except where a ride leaves or arrives; a moving car is
   * drawn round each rider. Call with every rider's position each frame, then `endRides`. */
  ride(index: number, x: number, feet: number, from: number, to: number): void {
    this.away.push(from, to);
    let image = this.riding[index];
    if (!image) {
      image = this.scene.add.image(0, 0, this.carKey ?? '').setOrigin(0.5, 1).setDepth(DEPTH.car);
      this.tints.add('inside', image);
      this.riding[index] = image;
    }
    image.setPosition(x, feet).setVisible(this.shown);
  }

  endRides(count: number): void {
    for (let i = count; i < this.riding.length; i++) this.riding[i].setVisible(false);
    for (const car of this.cars) car.image.setVisible(this.shown && !this.away.includes(car.floorLine));
    this.away.length = 0;
  }

  /** Hangs each painting the server has in this building's frames. */
  hang(frames: readonly Frame[], load: (url: string) => Promise<string>): void {
    for (const hung of this.frames.values()) {
      const painting = frames.find(({ map, id }) => map === hung.map && id === hung.id)?.painting;
      hung.image?.destroy();
      hung.image = undefined;
      if (!painting) {
        this.fit(hung, EMPTY_ASPECT);
        continue;
      }
      void load(painting.image).then((texture) => {
        if (!this.frames.has(`${hung.map}/${hung.id}`) || hung.image) return;
        const image = this.scene.add.image(hung.x, hung.y, texture).setDepth(DEPTH.painting);
        hung.image = this.tints.add('inside', image.setVisible(this.shown));
        this.fit(hung, image.width / image.height);
      });
    }
  }

  /** Stretches a frame's moulding round a painting of `aspect`, as tall as it can be. */
  private fit(hung: Hung, aspect: number): void {
    const { frame, shadow, image } = hung;
    if (!frame) return;
    const sides = MOULDING.left + MOULDING.right;
    const tall = frame.frame.realHeight;
    const opening = tall - MOULDING.top - MOULDING.bottom;
    const wide = opening * aspect + sides;
    const scale = Math.min((FRAME_M * PPM) / tall, hung.maxWidth / wide);
    frame.setSize(wide, tall).setScale(scale);
    if (shadow) shadow.setScale((wide * scale) / frame.frame.realWidth / 0.5, (tall * scale) / tall / 0.5);
    const dx = ((MOULDING.left - MOULDING.right) / 2) * scale;
    const dy = ((MOULDING.top - MOULDING.bottom) / 2) * scale;
    image?.setPosition(hung.x + dx, hung.y + dy).setDisplaySize(opening * aspect * scale, opening * scale);
  }

  destroy(): void {
    for (const image of [...this.images, ...this.riding]) image.destroy();
    for (const hung of this.frames.values()) {
      for (const part of [hung.frame, hung.shadow, hung.image]) part?.destroy();
    }
  }

  private add(image: Phaser.GameObjects.Image, depth: number): Phaser.GameObjects.Image {
    this.images.push(image.setDepth(depth));
    return this.tints.add('inside', image);
  }

  private floor(
    { map, floorLine, ceiling }: Dollhouse['floors'][number],
    paper: string | undefined,
    village: Village,
  ): void {
    const { box, scene, textures, manifest } = this;
    const [left, right] = [box.left + TILE, box.right - TILE];
    if (paper) {
      const piece = manifest.pieces[paper];
      const scale = (piece.height * PPM) / piece.size[1];
      const step = piece.size[1] * scale;
      for (let y = ceiling; y < floorLine - 0.5; y += step) {
        for (const image of tileAlong(scene, textures.key(paper), { width: piece.size[0] }, left, right, y, scale)) {
          const width = Math.min(piece.size[0], (right - image.x) / scale);
          if (y + step > floorLine) image.setCrop(0, 0, width, (floorLine - y) / scale);
          this.add(image, DEPTH.room);
        }
      }
      const shade = scene.add.image(left, ceiling, textures.roomShade()).setOrigin(0, 0);
      this.images.push(shade.setDisplaySize(right - left, floorLine - ceiling).setDepth(DEPTH.roomShade));
    }
    const paintings = map.interactables.filter(({ type }) => type === 'painting');
    if (paintings.length === 0) {
      for (const share of WINDOWS) {
        const x = box.left + (box.right - box.left) * share;
        const y = (map.offset.y + WINDOW_ROW) * TILE;
        this.sprite(manifest.platforms.window, x, y, [0.5, 0.5], DEPTH.window);
      }
    }
    for (const painting of paintings) {
      const x = (map.offset.x + painting.x + painting.w / 2) * TILE;
      const y = (map.offset.y + painting.y + painting.h / 2) * TILE;
      const hung: Hung = { map: map.id, id: painting.name, x, y, maxWidth: painting.w * TILE * FRAME_FILL };
      const key = manifest.furniture.picture_frame?.piece;
      if (key) {
        const { left, right, top, bottom } = MOULDING;
        const frame = scene.add.nineslice(x, y, textures.key(key), undefined, 0, 0, left, right, top, bottom);
        hung.frame = this.tints.add('inside', frame.setDepth(DEPTH.frame));
        hung.shadow = dropShadow(scene, textures, key, [0.5, 0.5], x, y, { ppm: PPM, alpha: 0.3 });
        hung.shadow.setDepth(DEPTH.frame - 0.05);
      }
      this.frames.set(`${map.id}/${painting.name}`, hung);
      this.fit(hung, EMPTY_ASPECT);
    }
    for (const item of map.furniture) this.furniture(item, map);
    for (const link of map.links) {
      if (link.side !== 'outside' || link.kind === 'door') continue;
      const across = crossing(village, link);
      if (!across) continue;
      const [low, high] = [across.path.points[0], across.path.points.at(-1)!];
      if (link.kind === 'stairs') {
        const key = manifest.platforms.stairs;
        const piece = manifest.pieces[key];
        const width = Math.abs(high.x - low.x) * TILE + 0.4 * TILE;
        const height = (STOREY_M + STAIRS_RAIL_M) * PPM;
        const image = scene.add
          .image(xOf((low.x + high.x) / 2), feetOf(low.y), textures.key(key))
          .setOrigin(0.5, 1)
          .setScale(width / piece.size[0], height / piece.size[1])
          .setFlipX(high.x < low.x);
        this.add(image, DEPTH.stairs);
        this.shadowOf(image, key);
      } else if (link.kind === 'ladder') {
        const key = manifest.platforms.ladder;
        const piece = manifest.pieces[key];
        const height = (low.y - high.y) * TILE + LADDER_ABOVE_M * PPM;
        const image = scene.add.image(xOf(low.x), feetOf(low.y), textures.key(key)).setOrigin(0.5, 1);
        this.add(image.setScale(1, height / piece.size[1]), DEPTH.stairs);
        this.shadowOf(image, key);
      }
    }
  }

  private furniture(item: Placed, map: SideMap): void {
    const { manifest, scene, textures } = this;
    let key = furnitureKey(manifest, item, map.id);
    if (!key) return;
    const place = furniturePlacement(item, map);
    if (item.name === 'lift') {
      const shaft = manifest.platforms.lift_shaft;
      const piece = manifest.pieces[shaft];
      const floorLine = (map.offset.y + 3) * TILE;
      const scale = (STOREY_M * PPM) / piece.size[1];
      const room = (floorLine - this.box.top) / scale;
      const image = scene.add.image(place.x, floorLine, textures.key(shaft)).setOrigin(0.5, 1).setScale(scale);
      if (room < piece.size[1]) image.setCrop(0, piece.size[1] - room, piece.size[0], room);
      this.add(image, DEPTH.shaft);
      this.carKey = textures.key(key);
      const car = this.add(scene.add.image(place.x, place.y, this.carKey).setOrigin(0.5, 1), DEPTH.car);
      this.cars.push({ image: car, floorLine: (map.offset.y + 3) * TILE });
      return;
    }
    if (manifest.furniture[item.name]?.stretch) key = textures.stretched(key, stretchWidth(item)).name;
    const anchor = [place.originX, place.originY] as const;
    const onWall = place.originY < 1;
    const shadow = dropShadow(scene, textures, key, anchor, place.x, place.y, { ppm: PPM });
    this.images.push(shadow.setDepth(onWall ? DEPTH.frame - 0.05 : DEPTH.furnitureShadow));
    const image = scene.add.image(place.x, place.y, textures.key(key)).setOrigin(...anchor);
    this.add(image, onWall ? DEPTH.frame : DEPTH.furniture);
  }

  /** A drop shadow for a stretched or mirrored piece, matching its scale. */
  private shadowOf(image: Phaser.GameObjects.Image, key: string): void {
    const shadow = dropShadow(this.scene, this.textures, key, [image.originX, image.originY], image.x, image.y, {
      ppm: PPM,
      alpha: 0.3,
      flip: image.flipX,
    });
    this.images.push(shadow.setScale(image.scaleX / 0.5, image.scaleY / 0.5).setDepth(image.depth - 0.05));
  }

  private sprite(key: string, x: number, y: number, anchor: readonly [number, number], depth: number): void {
    const image = this.scene.add.image(x, y, this.textures.key(key)).setOrigin(...anchor);
    this.shadowOf(this.add(image, depth), key);
  }

  private slabs(): void {
    const { box, scene, textures, manifest } = this;
    const width = Math.round(box.right - box.left);
    const thick = Math.round(SLAB_M * PPM);
    const band = textures.band(manifest.slab, width, thick);
    const lines = [...box.floors.map(({ floorLine }) => floorLine), box.top];
    for (const y of lines) {
      const image = scene.add.image(box.left, y, band.key).setOrigin(0, y === box.top ? 1 : 0);
      this.add(image, DEPTH.slab);
    }
    const tall = Math.round(box.ground - box.top + thick);
    const post = textures.band(manifest.slab, tall, thick);
    for (const x of [box.left, box.right - thick]) {
      const image = scene.add.image(x, box.ground + thick, post.key).setOrigin(0, 0).setAngle(-90);
      this.add(image, DEPTH.slab);
    }
  }
}
