import Phaser from 'phaser';
import type { DollManifest } from '../dolls/manifest';
import { standingHeight, type Posed } from '../dolls/rig';
import { DOLL_M, PPM } from './layout';
import type { Drawn } from './motion';
import { facesLeft, PoseCache } from './poses';

const SHADOW = 0x140e0a;
const SHADOW_ALPHA = 0.3;

/** A paper doll posed from a cache, so drawing it each frame allocates nothing. Like the rig's
 * `PaperDoll`, each piece casts a small shadow on those behind it, and the far limbs are darker;
 * here every piece is also tinted by the time of day. Its origin is on the ground under its hips. */
export class SideDoll extends Phaser.GameObjects.Container {
  readonly doll: DollManifest;
  private readonly cache: PoseCache;
  private readonly size: number;
  private key: string;
  private readonly slots: [Phaser.GameObjects.Image, Phaser.GameObjects.Image][] = [];
  private shown?: Posed;
  private flipped = false;
  private tint = -1;

  constructor(scene: Phaser.Scene, doll: DollManifest, key: string, height = DOLL_M * PPM) {
    super(scene, 0, 0);
    this.doll = doll;
    this.key = key;
    this.cache = new PoseCache(doll);
    this.size = height / standingHeight(doll);
  }

  paint(key: string): void {
    this.key = key;
    this.shown = undefined;
  }

  /** Poses the doll as `drawn` says, in `tint`. Does nothing if neither has changed. */
  show({ pose, facing, phase, seated, on }: Drawn, tint: number): this {
    const posed = this.cache.get(pose, facing, phase, seated, on);
    const flip = posed.view === 'side' && facesLeft(facing);
    if (posed === this.shown && flip === this.flipped && tint === this.tint) return this;
    this.shown = posed;
    this.flipped = flip;
    this.tint = tint;
    this.setScale(flip ? -this.size : this.size, this.size);
    const nudge = this.doll.unit * 0.5;
    const r = (tint >> 16) & 255;
    const g = (tint >> 8) & 255;
    const b = tint & 255;
    const { parts } = posed;
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      const slot = this.slot(i);
      this.place(slot[0], part).setPosition(part.x + nudge, part.y + nudge * 1.4).setVisible(i > 0);
      const s = part.shade;
      this.place(slot[1], part)
        .setPosition(part.x, part.y)
        .setTint(Phaser.Display.Color.GetColor(Math.round(r * s), Math.round(g * s), Math.round(b * s)));
    }
    for (let i = parts.length; i < this.slots.length; i++) {
      this.slots[i][0].setVisible(false);
      this.slots[i][1].setVisible(false);
    }
    return this;
  }

  private place(image: Phaser.GameObjects.Image, part: Posed['parts'][number]): Phaser.GameObjects.Image {
    const { frame, pivot } = this.doll.pieces[part.piece];
    return image
      .setTexture(this.key, part.piece)
      .setOrigin(pivot[0] / frame[2], pivot[1] / frame[3])
      .setAngle(part.angle)
      .setScale(1, part.scaleY)
      .setVisible(true);
  }

  private slot(i: number): [Phaser.GameObjects.Image, Phaser.GameObjects.Image] {
    while (this.slots.length <= i) {
      const shadow = new Phaser.GameObjects.Image(this.scene, 0, 0, this.key, 'torso');
      shadow.setTintFill(SHADOW).setAlpha(SHADOW_ALPHA);
      const image = new Phaser.GameObjects.Image(this.scene, 0, 0, this.key, 'torso');
      this.add([shadow, image]);
      this.slots.push([shadow, image]);
    }
    return this.slots[i];
  }
}
