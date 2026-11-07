import type Phaser from 'phaser';
import { playerState, type Corpse, type Pile, type Position } from '../net';
import { iconUrl } from '../ui/icons';
import { clues } from '../world/clues';
import { reachables, wayPrompts } from '../world/reach';
import { PPM } from './layout';
import { sameCorpses, sameItems } from './piles';
import type { Content, StreetView } from './street-view';
import type { SideTextures } from './textures';
import { glowKey, glowing, spritesOf, usablesOn, type Sprite, type Usable } from './usables';

const GLOW = { colour: '#fff3b8', px: 7, alpha: 0.75, pulse: 0.2, seconds: 1.6 };
const TICK = { colour: 0xe8572a, outline: 0x2b2118, m: 0.36, width: 0.055 };

type Shown = { usable: Usable; images: Phaser.GameObjects.Image[]; tick?: Phaser.GameObjects.Graphics };
type Glow = { images: Phaser.GameObjects.Image[]; textures: string[] };

export type DrawnUsable = { id: string; kind: string; map: string; x: number; y: number; shown: boolean; glowing: boolean; searched: boolean; recipe: boolean };

/** Draws what E uses where nothing else does, and a glow round the one E uses where the player stands. */
export class UsableView {
  private shown: Shown[] = [];
  private readonly glows = new Map<string, Glow>();
  private glowing?: string;
  private drawnFor?: { street: StreetView; searched: string; jacked: boolean; piles: readonly Pile[]; corpses: readonly Corpse[] };
  private readonly scene: Phaser.Scene;
  private readonly textures: SideTextures;

  constructor(scene: Phaser.Scene, textures: SideTextures) {
    this.scene = scene;
    this.textures = textures;
  }

  update(content: Content, street: StreetView, player: Position | undefined, seconds: number): void {
    const searched = playerState.latest?.player.searched ?? [];
    const piles = reachables.piles();
    const corpses = playerState.latest?.player.corpses ?? [];
    const jacked = !!reachables.jacked?.();
    const drawn = this.drawnFor;
    const same = drawn?.street === street && drawn.searched === searched.join() && drawn.jacked === jacked;
    if (!same || !sameItems(drawn.piles, piles) || !sameCorpses(drawn.corpses, corpses)) {
      if (drawn?.street !== street) this.unglow();
      this.clear();
      const usables = usablesOn(content.village, content.scenery, street.map, { searched, piles, corpses, clues, jacked });
      this.shown = usables.map((usable) => ({ usable, images: [] }));
      this.drawnFor = { street, searched: searched.join(), jacked, piles, corpses };
    }
    for (const shown of this.shown) this.show(shown, street);
    this.light(glowing(player, wayPrompts()), street, seconds);
  }

  drawn(): DrawnUsable[] {
    return this.shown.map(({ usable, images, tick }) => ({
      id: usable.id,
      kind: usable.kind,
      map: usable.map,
      x: usable.picture.x,
      y: usable.picture.y,
      shown: 'piece' in usable.picture || images.some((image) => image.visible),
      glowing: this.glowing === glowKey(usable) && !!this.glows.get(glowKey(usable))?.images[0]?.visible,
      searched: !!tick,
      recipe: !!usable.loot?.some(({ icon }) => icon === 'schematic'),
    }));
  }

  destroy(): void {
    this.clear();
    this.unglow();
  }

  private clear(): void {
    for (const { images, tick } of this.shown) {
      for (const image of images) image.destroy();
      tick?.destroy();
    }
    this.shown = [];
    this.drawnFor = undefined;
  }

  private show(shown: Shown, street: StreetView): void {
    const { usable } = shown;
    const visible = !usable.building || street.isOpen(usable.building);
    const tint = street.tints.colours[usable.building ? 'inside' : 'ground'];
    if (!shown.images.length) {
      const images = spritesOf(usable)
        .filter((sprite) => 'icon' in sprite)
        .map((sprite) => this.image(sprite));
      if (images.every(Boolean)) shown.images = images as Phaser.GameObjects.Image[];
      else images.forEach((image) => image?.destroy());
    }
    for (const image of shown.images) image.setVisible(visible).setTint(tint);
    if (usable.searched && !shown.tick) shown.tick = this.tick(usable.searched);
    shown.tick?.setVisible(visible);
  }

  /** Undefined until its texture has loaded. */
  private image(sprite: Sprite): Phaser.GameObjects.Image | undefined {
    const key = this.texture(sprite);
    if (!key) return undefined;
    const image = this.scene.add.image(sprite.x, sprite.y, key).setOrigin(sprite.originX, sprite.originY).setDepth(sprite.depth);
    return 'icon' in sprite ? image.setScale(sprite.height / image.height) : image;
  }

  private texture(sprite: Sprite): string | undefined {
    if ('piece' in sprite) {
      const key = this.textures.key(sprite.piece);
      if (!this.scene.textures.exists(key)) return undefined;
      return sprite.stretch ? this.textures.stretched(sprite.piece, sprite.stretch).key : key;
    }
    const key = this.textures.key(`icon:${sprite.icon}`);
    if (this.scene.textures.exists(key)) return key;
    const url = iconUrl(sprite.icon);
    if (url) void this.textures.load(`icon:${sprite.icon}`, url);
    return undefined;
  }

  private tick({ x, y, depth }: { x: number; y: number; depth: number }): Phaser.GameObjects.Graphics {
    const size = TICK.m * PPM;
    const points = [
      { x: -0.45 * size, y: 0 },
      { x: -0.1 * size, y: 0.35 * size },
      { x: 0.5 * size, y: -0.45 * size },
    ];
    const tick = this.scene.add.graphics({ x, y }).setDepth(depth);
    tick.lineStyle(TICK.width * PPM * 1.8, TICK.outline, 0.55).strokePoints(points);
    tick.lineStyle(TICK.width * PPM, TICK.colour, 0.95).strokePoints(points);
    return tick;
  }

  private light(id: string | undefined, street: StreetView, seconds: number): void {
    const shown = id ? this.shown.find(({ usable }) => usable.id === id) : undefined;
    const key = shown && glowKey(shown.usable);
    if (this.glowing !== key) this.glows.get(this.glowing ?? '')?.images.forEach((image) => image.setVisible(false));
    this.glowing = key;
    if (!shown || !key) return;
    let glow = this.glows.get(key);
    if (!glow) {
      glow = this.glowAround(shown.usable, key);
      if (!glow) return;
      this.glows.set(key, glow);
    }
    const visible = !shown.usable.building || street.isOpen(shown.usable.building);
    const alpha = GLOW.alpha + GLOW.pulse * Math.sin((seconds / GLOW.seconds) * Math.PI * 2);
    for (const image of glow.images) image.setVisible(visible).setAlpha(alpha);
  }

  /** An outline of each of its pictures, blurred, just behind them all. */
  private glowAround(usable: Usable, key: string): Glow | undefined {
    const sprites = spritesOf(usable);
    const sources = sprites.map((sprite) => this.texture(sprite));
    if (!sources.every(Boolean)) return undefined;
    const depth = Math.min(...sprites.map(({ depth }) => depth)) - 0.01;
    const textures = sprites.map((_, i) => `usable-glow:${key}:${i}`);
    return { images: sprites.map((sprite, i) => this.outline(sprite, sources[i]!, textures[i], depth)), textures };
  }

  private outline(sprite: Sprite, source: string, texture: string, depth: number): Phaser.GameObjects.Image {
    const image = this.scene.textures.get(source).getSourceImage() as HTMLImageElement | HTMLCanvasElement;
    const scale = 'icon' in sprite ? sprite.height / image.height : 1;
    const reach = GLOW.px / scale;
    const pad = Math.ceil(2 * reach);
    const canvas = document.createElement('canvas');
    canvas.width = image.width + 2 * pad;
    canvas.height = image.height + 2 * pad;
    const context = canvas.getContext('2d')!;
    context.filter = `blur(${reach / 2}px)`;
    for (let i = 0; i < 12; i++) {
      const angle = (i / 12) * Math.PI * 2;
      context.drawImage(image, pad + Math.cos(angle) * reach, pad + Math.sin(angle) * reach);
    }
    context.filter = 'none';
    context.globalCompositeOperation = 'source-in';
    context.fillStyle = GLOW.colour;
    context.fillRect(0, 0, canvas.width, canvas.height);
    if (this.scene.textures.exists(texture)) this.scene.textures.remove(texture);
    this.scene.textures.addCanvas(texture, canvas);
    return this.scene.add
      .image(sprite.x, sprite.y, texture)
      .setOrigin((pad + sprite.originX * image.width) / canvas.width, (pad + sprite.originY * image.height) / canvas.height)
      .setScale(scale)
      .setDepth(depth);
  }

  private unglow(): void {
    for (const { images, textures } of this.glows.values()) {
      images.forEach((image) => image.destroy());
      textures.forEach((texture) => this.scene.textures.remove(texture));
    }
    this.glows.clear();
    this.glowing = undefined;
  }
}
