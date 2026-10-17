import Phaser from 'phaser';
import type { Position } from '../net';
import { PLAYER_ID, type ScreenBox, type ScreenPoint } from '../ui/world-view';
import type { Body, Point } from '../world';
import { framePixel } from '../world/hit';
import {
  CONTACT_ALPHA,
  contactShadow,
  directionFor,
  dropShadow,
  feetOf,
  SHADOW_DEPTH,
  sheetFor,
  sheetFrame,
  tintColour,
  walkTimeScale,
  type CharacterManifest,
  type Figure,
  type IsoTile,
  type Layer,
  type LightingSet,
  type ResidentLight,
  type SetLight,
  type ShadowMask,
  type SpriteFrame,
} from '../world/iso';

/** Where the characters' sprites come from: `sheetArt` is #141's sheets. */
export interface CharacterArt {
  /** Every character's, as drawn. */
  readonly frame: SpriteFrame;
  load(scene: Phaser.Scene): Promise<void>;
  add(scene: Phaser.Scene, id: string): Puppet;
}

/** A character's sprite, with its origin at the feet. */
export type Puppet = {
  sprite: Phaser.GameObjects.Sprite;
  /** After a step on the map, at `speed` tiles a second. */
  pose(step: Point, walking: boolean, speed: number): void;
};

type Character = {
  puppet: Puppet;
  contact: Phaser.GameObjects.Image;
  shadows: Map<LightingSet, Phaser.GameObjects.Image>;
  last: Position;
};

const CONTACT_KEY = 'iso-shadow/contact';
const shadowKey = (set: LightingSet) => `iso-shadow/${set}`;

/** Draws characters from any `CharacterArt`, lit and shadowed by the sets they stand in. */
export class IsoCharacters {
  readonly frame: SpriteFrame;
  private readonly scene: Phaser.Scene;
  private readonly tile: IsoTile;
  private readonly art: CharacterArt;
  private readonly lights: Record<LightingSet, SetLight>;
  private readonly characters = new Map<string, Character>();

  private constructor(
    scene: Phaser.Scene,
    tile: IsoTile,
    art: CharacterArt,
    lights: Record<LightingSet, SetLight>,
  ) {
    this.scene = scene;
    this.tile = tile;
    this.art = art;
    this.frame = art.frame;
    this.lights = lights;
    addMask(scene, CONTACT_KEY, contactShadow(tile));
  }

  static async load(
    scene: Phaser.Scene,
    tile: IsoTile,
    art: CharacterArt,
    lights: Record<LightingSet, SetLight>,
  ): Promise<IsoCharacters> {
    await art.load(scene);
    return new IsoCharacters(scene, tile, art, lights);
  }

  draw(
    bodies: ReadonlyMap<string, Body>,
    dt: number,
    figureAt: (position: Position) => Figure,
    layers: readonly Layer[],
    lightAt: (feet: Position) => ResidentLight,
  ): void {
    for (const [id, body] of bodies) {
      const character = this.characters.get(id) ?? this.add(id, body.position);
      const { x, y } = body.position;
      const step = { x: x - character.last.x, y: y - character.last.y };
      character.last = { x, y };
      character.puppet.pose(step, body.walking, Math.hypot(step.x, step.y) / dt);

      const figure = figureAt(body.position);
      const light = lightAt(feetOf(body.position));
      const { sprite } = character.puppet;
      sprite.setPosition(figure.x, figure.bottom).setDepth(figure.depth).setTint(tintColour(light.tint));
      character.contact.setPosition(figure.x, figure.bottom);
      this.shade(character, figure, layers, light.shadows);
    }
    for (const [id, character] of this.characters) {
      if (bodies.has(id)) continue;
      character.puppet.sprite.destroy();
      character.contact.destroy();
      for (const shadow of character.shadows.values()) shadow.destroy();
      this.characters.delete(id);
    }
  }

  /** `box` is `figureBox`: the frame down to the feet. */
  opaqueAt(id: string, box: ScreenBox, point: ScreenPoint): boolean {
    const sprite = this.characters.get(id)?.puppet.sprite;
    if (!sprite) return false;
    const { frame } = sprite;
    const rows = (frame.height * this.frame.anchor.y) / this.frame.height;
    const { x, y } = framePixel(point, box, { width: frame.width, height: rows });
    return (this.scene.textures.getPixelAlpha(x, y, sprite.texture.key, frame.name) ?? 0) > 0;
  }

  /** Builds a set's drop shadow while it loads, rather than in the first frame of its fade. */
  prepare(set: LightingSet): void {
    const key = shadowKey(set);
    if (this.scene.textures.exists(key)) return;
    addMask(this.scene, key, dropShadow(this.lights[set].shadow, this.tile));
  }

  private shade(character: Character, figure: Figure, layers: readonly Layer[], alphas: number[]): void {
    for (const shadow of character.shadows.values()) shadow.setVisible(false);
    layers.forEach(({ set }, i) => {
      const shadow = character.shadows.get(set) ?? this.addShadow(character, set);
      shadow.setPosition(figure.x, figure.bottom).setAlpha(alphas[i]).setVisible(alphas[i] > 0);
    });
  }

  private add(id: string, position: Position): Character {
    const character = {
      puppet: this.art.add(this.scene, id),
      contact: this.shadowImage(CONTACT_KEY).setAlpha(CONTACT_ALPHA),
      shadows: new Map(),
      last: { ...position },
    };
    this.characters.set(id, character);
    return character;
  }

  private addShadow(character: Character, set: LightingSet): Phaser.GameObjects.Image {
    this.prepare(set);
    const shadow = this.shadowImage(shadowKey(set));
    character.shadows.set(set, shadow);
    return shadow;
  }

  private shadowImage(key: string): Phaser.GameObjects.Image {
    const { origin, width, height } = this.scene.textures.get(key).customData as ShadowMask;
    return this.scene.add
      .image(0, 0, key)
      .setOrigin(origin.x / width, origin.y / height)
      .setDepth(SHADOW_DEPTH);
  }
}

function addMask(scene: Phaser.Scene, key: string, mask: ShadowMask): void {
  const texture = scene.textures.createCanvas(key, mask.width, mask.height)!;
  const pixels = texture.context.createImageData(mask.width, mask.height);
  mask.alpha.forEach((alpha, i) => (pixels.data[i * 4 + 3] = alpha));
  texture.context.putImageData(pixels, 0, 0);
  texture.refresh();
  texture.setFilter(Phaser.Textures.FilterMode.LINEAR);
  texture.customData = mask;
}

const MIN_TIME_SCALE = 0.25;
const MAX_TIME_SCALE = 4;
const FIRST_DIRECTION = 'se';

const sheetKey = (id: string) => `iso-character/${id}`;
const animationKey = (sheet: string, name: string, direction: string) => `${sheet}/${name}/${direction}`;

/** #141's 3D sheets: 8 directions, a walk and an idle, all in one frame size. */
export function sheetArt(
  manifest: CharacterManifest,
  tile: IsoTile,
  sheetUrl: (image: string) => string | undefined,
  loadImage: (url: string) => Promise<HTMLImageElement>,
): CharacterArt {
  const frame = sheetFrame(manifest, tile);
  const sheets = Object.keys(manifest.characters);
  const { walk } = manifest.animations;

  const load = async (scene: Phaser.Scene) => {
    const { width: frameWidth, height: frameHeight } = manifest.frame;
    await Promise.all(
      Object.entries(manifest.characters).map(async ([id, { image }]) => {
        const source = await loadImage(sheetUrl(image)!);
        scene.textures.addSpriteSheet(sheetKey(id), source, { frameWidth, frameHeight });
        for (const { name: direction } of manifest.directions) {
          for (const name of ['walk', 'idle'] as const) {
            const { fps, frames } = manifest.animations[name];
            scene.anims.create({
              key: animationKey(id, name, direction),
              frames: scene.anims.generateFrameNumbers(sheetKey(id), { frames: frames[direction] }),
              frameRate: fps,
              repeat: -1,
            });
          }
        }
      }),
    );
  };

  const add = (scene: Phaser.Scene, id: string): Puppet => {
    const sheet = sheetFor(id, sheets, PLAYER_ID);
    const sprite = scene.add
      .sprite(0, 0, sheetKey(sheet))
      .setOrigin(frame.anchor.x / frame.width, frame.anchor.y / frame.height);
    let direction = FIRST_DIRECTION;
    const pose = (step: Point, walking: boolean, speed: number) => {
      direction = directionFor(step, manifest.directions, direction);
      const key = animationKey(sheet, walking ? 'walk' : 'idle', direction);
      const current = sprite.anims.currentAnim?.key;
      if (current !== key) {
        const stride = walking && current?.startsWith(`${sheet}/walk/`);
        sprite.play({ key, startFrame: stride ? sprite.anims.currentFrame!.index - 1 : 0 });
      }
      if (!walking) sprite.anims.timeScale = 1;
      else if (speed > 0) {
        const scale = walkTimeScale(speed, walk);
        sprite.anims.timeScale = Phaser.Math.Clamp(scale, MIN_TIME_SCALE, MAX_TIME_SCALE);
      }
    };
    return { sprite, pose };
  };

  return { frame, load, add };
}
