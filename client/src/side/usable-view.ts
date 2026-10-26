import type Phaser from 'phaser';
import { playerState, type Pile, type Position } from '../net';
import { iconUrl } from '../ui/icons';
import { clues } from '../world/clues';
import { reachables, wayPrompts } from '../world/reach';
import { PPM } from './layout';
import type { Content, StreetView } from './street-view';
import type { SideTextures } from './textures';
import { glowing, usablesOn, type Sprite, type Usable } from './usables';

/** World px out from its edge, and its alpha from `alpha - pulse` to `alpha + pulse`. */
const GLOW = { colour: '#fff3b8', px: 7, alpha: 0.75, pulse: 0.2, seconds: 1.6 };
const TICK = { colour: 0xe8572a, outline: 0x2b2118, m: 0.36, width: 0.055 };

type Shown = { usable: Usable; images: Phaser.GameObjects.Image[]; tick?: Phaser.GameObjects.Graphics };
type Glow = { id: string; image: Phaser.GameObjects.Image; texture: string };

/** What the harness and the walk read: each usable thing on the street shown, and whether it glows. */
export type DrawnUsable = { id: string; kind: string; map: string; x: number; y: number; shown: boolean; glowing: boolean; searched: boolean; recipe: boolean };

/** Draws what E uses where nothing else does, and a glow round the one E uses where the player stands. */
export class UsableView {
  private shown: Shown[] = [];
  private glow?: Glow;
  private drawnFor?: { street: StreetView; searched: string; piles: readonly Pile[] };
  private readonly scene: Phaser.Scene;
  private readonly textures: SideTextures;

  constructor(scene: Phaser.Scene, textures: SideTextures) {
    this.scene = scene;
    this.textures = textures;
  }

  update(content: Content, street: StreetView, player: Position | undefined, seconds: number): void {
    const searched = playerState.latest?.player.searched ?? [];
    const piles = reachables.piles();
    const drawn = this.drawnFor;
    if (drawn?.street !== street || drawn.searched !== searched.join() || !same(drawn.piles, piles)) {
      this.clear();
      const usables = usablesOn(content.village, content.scenery, street.map, { searched, piles, clues });
      this.shown = usables.map((usable) => ({ usable, images: [] }));
      this.drawnFor = { street, searched: searched.join(), piles };
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
      glowing: this.glow?.id === usable.id && this.glow.image.visible,
      searched: !!tick,
      recipe: !!usable.recipe,
    }));
  }

  destroy(): void {
    this.clear();
  }

  private clear(): void {
    for (const { images, tick } of this.shown) {
      for (const image of images) image.destroy();
      tick?.destroy();
    }
    this.shown = [];
    this.unglow();
    this.drawnFor = undefined;
  }

  private show(shown: Shown, street: StreetView): void {
    const { usable } = shown;
    const visible = !usable.building || street.isOpen(usable.building);
    const tint = street.tints.colours[usable.building ? 'inside' : 'ground'];
    if (!shown.images.length) {
      const sprites = [usable.picture, usable.recipe].filter((sprite): sprite is Sprite => !!sprite && 'icon' in sprite);
      const images = sprites.map((sprite) => this.image(sprite));
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
    if (this.glow && this.glow.id !== shown?.usable.id) this.unglow();
    if (!shown) return;
    this.glow ??= this.glowAround(shown.usable);
    if (!this.glow) return;
    const visible = !shown.usable.building || street.isOpen(shown.usable.building);
    this.glow.image.setVisible(visible).setAlpha(GLOW.alpha + GLOW.pulse * Math.sin((seconds / GLOW.seconds) * Math.PI * 2));
  }

  /** An outline of the picture, blurred, just behind it. */
  private glowAround(usable: Usable): Glow | undefined {
    const sprite = usable.picture;
    const source = this.texture(sprite);
    if (!source) return undefined;
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
    const texture = `usable-glow:${usable.id}`;
    if (this.scene.textures.exists(texture)) this.scene.textures.remove(texture);
    this.scene.textures.addCanvas(texture, canvas);
    const glow = this.scene.add
      .image(sprite.x, sprite.y, texture)
      .setOrigin((pad + sprite.originX * image.width) / canvas.width, (pad + sprite.originY * image.height) / canvas.height)
      .setScale(scale)
      .setDepth(sprite.depth - 0.01);
    return { id: usable.id, image: glow, texture };
  }

  private unglow(): void {
    if (!this.glow) return;
    this.glow.image.destroy();
    this.scene.textures.remove(this.glow.texture);
    this.glow = undefined;
  }
}

const same = (a: readonly Pile[], b: readonly Pile[]) => a.length === b.length && a.every((pile, i) => pile === b[i]);
