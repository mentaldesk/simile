import Phaser from 'phaser';
import type { Facing } from '../net/protocol';
import type { FigureManifest, SpriteFrame } from './manifest';
import type { DollPose, PoseOptions } from './rig';
import { placed, shown, type Shown } from './sprite';

/** The texture a frame is in: the figure's `key`, or its own for a frame with its own atlas. */
const textureOf = (key: string, name: string, { atlas }: SpriteFrame) => (atlas ? `${key}:${name}` : key);

function addAtlas(scene: Phaser.Scene, key: string, url: string, frames: [string, SpriteFrame][]): Promise<void> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => {
      const texture = scene.textures.exists(key) ? null : scene.textures.addImage(key, image);
      if (texture) {
        texture.setFilter(Phaser.Textures.FilterMode.LINEAR);
        for (const [name, { frame }] of frames) texture.add(name, 0, ...frame);
      }
      resolve();
    };
    image.onerror = () => reject(new Error(`Couldn't load the figure atlas ${url.slice(0, 80)}`));
    image.src = url;
  });
}

/** Frames with atlases of their own come in behind the figure's: until then, `draw` stands in for them. */
function addOwnAtlases(scene: Phaser.Scene, key: string, figure: FigureManifest): void {
  for (const [name, frame] of Object.entries(figure.frames)) {
    const own = textureOf(key, name, frame);
    if (frame.atlas && !scene.textures.exists(own)) addAtlas(scene, own, frame.atlas, [[name, frame]]).catch((error: unknown) => console.warn(error));
  }
}

/** Adds a figure's atlas to the scene's textures as `key`, with a frame for each painting. */
export function addFigureAtlas(scene: Phaser.Scene, key: string, figure: FigureManifest): Promise<void> {
  if (scene.textures.exists(key)) {
    addOwnAtlases(scene, key, figure);
    return Promise.resolve();
  }
  const url = figure.painted;
  if (!url) return Promise.reject(new Error(`${figure.id ?? 'A figure'} has no atlas`));
  const frames = Object.entries(figure.frames).filter(([, { atlas }]) => !atlas);
  return addAtlas(scene, key, url, frames).then(() => addOwnAtlases(scene, key, figure));
}

/** A resident painted whole, its origin on the ground under the middle of its head. `setPose`
 * is `PaperDoll`'s: each pose shows its painted frames by phase, mirrored to face west. */
export class SpriteFigure extends Phaser.GameObjects.Container {
  private worn: FigureManifest;
  private readonly image: Phaser.GameObjects.Image;
  private key: string;
  private size = 1;
  private posedAs?: Parameters<SpriteFigure['setPose']>;
  private drawn?: Shown;
  private asked?: FigureManifest;

  constructor(
    scene: Phaser.Scene,
    x: number,
    y: number,
    figure: FigureManifest,
    key: string,
    height = figure.height,
  ) {
    super(scene, x, y);
    this.worn = figure;
    this.key = key;
    this.image = new Phaser.GameObjects.Image(scene, 0, 0, key, figure.poses.stand[0]);
    this.add(this.image);
    this.setDollHeight(height);
    this.setPose('standing', 'east');
  }

  get figure(): FigureManifest {
    return this.worn;
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

  /** Draws another figure the same size once its atlas has loaded; the last one asked for wins. */
  async wear(figure: FigureManifest, key = `figure-${figure.id}`): Promise<void> {
    this.asked = figure;
    await addFigureAtlas(this.scene, key, figure);
    if (this.asked !== figure || !this.scene) return;
    const height = this.size * this.worn.height;
    this.worn = figure;
    this.setDollHeight(height);
    this.paint(key);
  }

  setPose(pose: DollPose, facing: Facing, phase = 0, options: PoseOptions = {}): this {
    this.posedAs = [pose, facing, phase, options];
    return this.draw(shown(this.figure, pose, facing, phase, options));
  }

  /** Does nothing unless the frame, its flip, bob, sway, seat, squash or shift changed. */
  draw(asked: Shown): this {
    const next = this.loaded(asked);
    const last = this.drawn;
    if (
      last &&
      last.frame === next.frame &&
      last.flip === next.flip &&
      last.bob === next.bob &&
      last.sway === next.sway &&
      last.seat === next.seat &&
      last.squash === next.squash &&
      last.shift === next.shift
    ) {
      return this;
    }
    this.drawn = next;
    const { originX, originY, x, y, angle } = placed(this.figure, next);
    const squash = next.squash ?? 0;
    this.image
      .setTexture(textureOf(this.key, next.frame, this.figure.frames[next.frame]), next.frame)
      .setOrigin(originX, originY)
      .setFlipX(next.flip)
      .setPosition(x, y)
      .setAngle(angle)
      .setScale(1 + squash / 2, 1 - squash);
    return this;
  }

  /** Standing, for a frame whose own atlas is still on its way. */
  private loaded(shown: Shown): Shown {
    const texture = textureOf(this.key, shown.frame, this.figure.frames[shown.frame]);
    return texture === this.key || this.scene.textures.exists(texture) ? shown : { ...shown, frame: this.figure.poses.stand[0] };
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
