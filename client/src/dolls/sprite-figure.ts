import Phaser from 'phaser';
import type { Facing } from '../net/protocol';
import type { FigureManifest } from './manifest';
import type { DollPose, PoseOptions } from './rig';
import { placed, shown, type Shown } from './sprite';

/** Adds a figure's atlas to the scene's textures as `key`, with a frame for each painting. */
export function addFigureAtlas(scene: Phaser.Scene, key: string, figure: FigureManifest): Promise<void> {
  if (scene.textures.exists(key)) return Promise.resolve();
  const url = figure.painted;
  if (!url) return Promise.reject(new Error(`${figure.id ?? 'A figure'} has no atlas`));
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => {
      const texture = scene.textures.exists(key) ? null : scene.textures.addImage(key, image);
      if (texture) {
        texture.setFilter(Phaser.Textures.FilterMode.LINEAR);
        for (const [name, { frame }] of Object.entries(figure.frames)) texture.add(name, 0, ...frame);
      }
      resolve();
    };
    image.onerror = () => reject(new Error(`Couldn't load the figure atlas ${url.slice(0, 80)}`));
    image.src = url;
  });
}

/** A resident painted whole, its origin on the ground under the middle of its head. `setPose`
 * is `PaperDoll`'s: each pose shows its painted frames by phase, mirrored to face west. */
export class SpriteFigure extends Phaser.GameObjects.Container {
  readonly figure: FigureManifest;
  private readonly image: Phaser.GameObjects.Image;
  private key: string;
  private size = 1;
  private posedAs?: Parameters<SpriteFigure['setPose']>;
  private drawn?: Shown;

  constructor(
    scene: Phaser.Scene,
    x: number,
    y: number,
    figure: FigureManifest,
    key: string,
    height = figure.height,
  ) {
    super(scene, x, y);
    this.figure = figure;
    this.key = key;
    this.image = new Phaser.GameObjects.Image(scene, 0, 0, key, figure.poses.stand[0]);
    this.add(this.image);
    this.setDollHeight(height);
    this.setPose('standing', 'east');
  }

  /** Scales the figure so it stands `height` pixels tall. */
  setDollHeight(height: number): this {
    this.size = height / this.figure.height;
    this.setScale(this.size);
    return this;
  }

  /** Another atlas with the same frames. */
  paint(key: string): this {
    this.key = key;
    this.drawn = undefined;
    if (this.posedAs) this.setPose(...this.posedAs);
    return this;
  }

  setPose(pose: DollPose, facing: Facing, phase = 0, options: PoseOptions = {}): this {
    this.posedAs = [pose, facing, phase, options];
    return this.draw(shown(this.figure, pose, facing, phase, options));
  }

  /** Does nothing unless the frame, its flip, bob, sway, seat or squash changed. */
  draw(next: Shown): this {
    const last = this.drawn;
    if (
      last &&
      last.frame === next.frame &&
      last.flip === next.flip &&
      last.bob === next.bob &&
      last.sway === next.sway &&
      last.seat === next.seat &&
      last.squash === next.squash
    ) {
      return this;
    }
    this.drawn = next;
    const { originX, originY, y, angle } = placed(this.figure, next);
    const squash = next.squash ?? 0;
    this.image
      .setTexture(this.key, next.frame)
      .setOrigin(originX, originY)
      .setFlipX(next.flip)
      .setPosition(0, y)
      .setAngle(angle)
      .setScale(1 + squash / 2, 1 - squash);
    return this;
  }

  setTint(tint: number): this {
    this.image.setTint(tint);
    return this;
  }
}

/** A figure in `scene` once its atlas has loaded. `id` names its texture. */
export async function makeFigure(
  scene: Phaser.Scene,
  x: number,
  y: number,
  id: string,
  figure: FigureManifest,
  height?: number,
): Promise<SpriteFigure> {
  const key = `figure-${id}`;
  await addFigureAtlas(scene, key, figure);
  const made = new SpriteFigure(scene, x, y, figure, key, height);
  scene.add.existing(made);
  return made;
}
