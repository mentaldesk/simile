import Phaser from 'phaser';
import { colour, layerTint, type Light } from './light';
import type { Placed } from './maps';
import type { Rgb, SceneryManifest } from './scenery';
import type { Derived, SideTextures } from './textures';

export type TintGroup = 'sky' | 'far' | 'mid' | 'near' | 'ground' | 'foreground' | 'inside';
type Tintable = { setTint(colour: number): unknown };

export class Tints {
  private readonly groups = new Map<TintGroup, Tintable[]>();
  private readonly fills: { rect: Phaser.GameObjects.Rectangle; base: number; group: TintGroup }[] = [];
  private readonly rgb: Rgb = [1, 1, 1];
  readonly colours: Record<TintGroup, number> = {
    sky: 0xffffff,
    far: 0xffffff,
    mid: 0xffffff,
    near: 0xffffff,
    ground: 0xffffff,
    foreground: 0xffffff,
    inside: 0xffffff,
  };

  add<T extends Tintable>(group: TintGroup, item: T): T {
    const items = this.groups.get(group) ?? [];
    items.push(item);
    this.groups.set(group, items);
    item.setTint(this.colours[group]);
    return item;
  }

  fill(group: TintGroup, rect: Phaser.GameObjects.Rectangle, base: number): Phaser.GameObjects.Rectangle {
    this.fills.push({ rect, base, group });
    rect.setFillStyle(multiply(base, this.colours[group]));
    return rect;
  }

  apply(light: Light): void {
    for (const group of Object.keys(this.colours) as TintGroup[]) {
      if (group === 'inside') this.colours.inside = colour(light.inside);
      else this.colours[group] = colour(layerTint(light, group, this.rgb));
    }
    for (const [group, items] of this.groups) {
      const tint = this.colours[group];
      for (const item of items) item.setTint(tint);
    }
    for (const { rect, base, group } of this.fills) rect.setFillStyle(multiply(base, this.colours[group]));
  }
}

export function multiply(a: number, b: number): number {
  const channel = (shift: number) => Math.round((((a >> shift) & 255) * ((b >> shift) & 255)) / 255);
  return (channel(16) << 16) | (channel(8) << 8) | channel(0);
}

export function placeDerived(
  scene: Phaser.Scene,
  derived: Derived,
  source: { width: number; height: number },
  anchor: readonly [number, number],
  x: number,
  y: number,
  scale = 1,
): Phaser.GameObjects.Image {
  return placeParts(scene, derived, source, anchor, x, y, scale)[0];
}

/** Each part anchored at (x, y), so they meet edge to edge. */
export function placeParts(
  scene: Phaser.Scene,
  derived: Pick<Derived, 'scale' | 'pad' | 'parts'>,
  source: { width: number; height: number },
  anchor: readonly [number, number],
  x: number,
  y: number,
  scale = 1,
): Phaser.GameObjects.Image[] {
  const left = derived.pad + anchor[0] * source.width * derived.scale;
  const height = Math.ceil(source.height * derived.scale) + 2 * derived.pad;
  const originY = (derived.pad + anchor[1] * source.height * derived.scale) / height;
  return derived.parts.map((part) =>
    scene.add
      .image(x, y, part.key)
      .setOrigin((left - part.x) / part.width, originY)
      .setScale(scale / derived.scale),
  );
}

export function tileAlong(
  scene: Phaser.Scene,
  key: string,
  frame: { frame?: string; width: number },
  x0: number,
  x1: number,
  y: number,
  scale: number,
): Phaser.GameObjects.Image[] {
  const step = frame.width * scale;
  const images: Phaser.GameObjects.Image[] = [];
  for (let x = x0; x < x1 - 0.5; x += step) {
    const image = scene.add.image(x, y, key, frame.frame).setOrigin(0, 0).setScale(scale);
    if (x + step > x1) image.setCrop(0, 0, (x1 - x) / scale, image.height);
    images.push(image);
  }
  return images;
}

/** Its colour variant is picked by where it is. */
export function furnitureKey(manifest: SceneryManifest, item: Placed, mapId: string): string | undefined {
  const entry = manifest.furniture[item.name];
  if (!entry) return undefined;
  const choices = [entry.piece, ...Object.values(entry.variants ?? {})];
  let hash = 0x811c9dc5;
  for (const c of `${mapId}:${item.x},${item.y}`) hash = Math.imul(hash ^ c.charCodeAt(0), 0x01000193);
  return choices[(hash >>> 0) % choices.length];
}

export const SHADOW_OFFSET_M = { x: 0.17, y: 0.12 };
export const SHADOW_ALPHA = 0.36;
const SHADOW = { scale: 0.5, blur: 8 };

export function dropShadow(
  scene: Phaser.Scene,
  textures: SideTextures,
  key: string,
  anchor: readonly [number, number],
  x: number,
  y: number,
  options: { scale?: number; blur?: number; ppm: number; alpha?: number; flip?: boolean },
): Phaser.GameObjects.Image {
  const source = scene.textures.get(textures.key(key)).getSourceImage();
  const derived = textures.shadow(key, options.scale ?? SHADOW.scale, options.blur ?? SHADOW.blur);
  return placeDerived(
    scene,
    derived,
    source,
    anchor,
    x + SHADOW_OFFSET_M.x * options.ppm,
    y + SHADOW_OFFSET_M.y * options.ppm,
  )
    .setAlpha(options.alpha ?? SHADOW_ALPHA)
    .setFlipX(options.flip ?? false);
}

/** It and its drop shadow, each in parts side by side if stretched wider than a texture can be. */
export function placeFurniture(
  scene: Phaser.Scene,
  textures: SideTextures,
  key: string,
  stretch: number | undefined,
  anchor: readonly [number, number],
  x: number,
  y: number,
  ppm: number,
): { images: Phaser.GameObjects.Image[]; shadows: Phaser.GameObjects.Image[] } {
  const name = stretch ? textures.stretched(key, stretch).name : key;
  const source = textures.size(name);
  const picture = { scale: 1, pad: 0, parts: textures.parts(name) };
  const shadow = textures.shadow(name, SHADOW.scale, SHADOW.blur);
  const [sx, sy] = [x + SHADOW_OFFSET_M.x * ppm, y + SHADOW_OFFSET_M.y * ppm];
  return {
    images: placeParts(scene, picture, source, anchor, x, y),
    shadows: placeParts(scene, shadow, source, anchor, sx, sy).map((image) => image.setAlpha(SHADOW_ALPHA)),
  };
}
