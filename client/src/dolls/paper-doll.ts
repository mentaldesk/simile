import Phaser from 'phaser';
import type { Facing } from '../net/protocol';
import { PIECES, type FlatDoll } from './manifest';
import { type DollPose, type PoseOptions, posed, standingHeight } from './rig';

const SHADOW = 0x140e0a;
const SHADOW_ALPHA = 0.3;

/** Adds a doll's atlas to the scene's textures as `key`, with a frame for each piece. */
export function addAtlas(
  scene: Phaser.Scene,
  key: string,
  url: string,
  doll: FlatDoll,
): Promise<void> {
  if (scene.textures.exists(key)) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => {
      const texture = scene.textures.exists(key) ? null : scene.textures.addImage(key, image);
      if (texture) {
        texture.setFilter(Phaser.Textures.FilterMode.LINEAR);
        for (const name of PIECES) {
          const [x, y, w, h] = doll.pieces[name].frame;
          texture.add(name, 0, x, y, w, h);
        }
      }
      resolve();
    };
    image.onerror = () => reject(new Error(`Couldn't load the doll atlas ${url.slice(0, 80)}`));
    image.src = url;
  });
}

/** A posed flat doll, its origin on the ground under its hips: the creator's preview while a
 * figure is painted. */
export class PaperDoll extends Phaser.GameObjects.Container {
  readonly doll: FlatDoll;
  readonly shadows: boolean;
  private readonly key: string;
  private size = 1;
  private readonly slots: [Phaser.GameObjects.Image, Phaser.GameObjects.Image][] = [];
  private posedAs?: Parameters<PaperDoll['setPose']>;

  constructor(
    scene: Phaser.Scene,
    x: number,
    y: number,
    doll: FlatDoll,
    flatKey: string,
    height = standingHeight(doll),
    shadows = true,
  ) {
    super(scene, x, y);
    this.doll = doll;
    this.shadows = shadows;
    this.key = flatKey;
    this.setDollHeight(height);
    this.setPose('standing', 'south');
  }

  /** Scales the doll so it stands `height` pixels tall. */
  setDollHeight(height: number): this {
    this.size = height / standingHeight(this.doll);
    if (this.posedAs) this.setPose(...this.posedAs);
    return this;
  }

  setPose(pose: DollPose, facing: Facing, phase = 0, options: PoseOptions = {}): this {
    this.posedAs = [pose, facing, phase, options];
    const { flip, parts } = posed(this.doll, pose, facing, phase, options);
    this.setScale(flip ? -this.size : this.size, this.size);
    const nudge = this.doll.unit * 0.5;
    parts.forEach((part, i) => {
      const [shadow, image] = this.slot(i);
      const spec = this.doll.pieces[part.piece];
      const [, , w, h] = spec.frame;
      for (const piece of [shadow, image]) {
        piece
          .setTexture(this.key, part.piece)
          .setOrigin(spec.pivot[0] / w, spec.pivot[1] / h)
          .setAngle(part.angle)
          .setScale(1, part.scaleY)
          .setVisible(true);
      }
      image.setPosition(part.x, part.y);
      const shade = Math.round(255 * part.shade);
      image.setTint(Phaser.Display.Color.GetColor(shade, shade, shade));
      shadow
        .setPosition(part.x + (flip ? -nudge : nudge), part.y + nudge * 1.4)
        .setVisible(this.shadows && i > 0);
    });
    for (const [shadow, image] of this.slots.slice(parts.length)) {
      shadow.setVisible(false);
      image.setVisible(false);
    }
    return this;
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

/** The flat doll in `scene`. `id` names its texture. */
export async function makeDoll(
  scene: Phaser.Scene,
  x: number,
  y: number,
  id: string,
  doll: FlatDoll,
  height?: number,
): Promise<PaperDoll> {
  const flat = `doll-${id}-flat`;
  await addAtlas(scene, flat, doll.flat, doll);
  const paper = new PaperDoll(scene, x, y, doll, flat, height);
  scene.add.existing(paper);
  return paper;
}
