import Phaser from 'phaser';
import type { Position } from '../net';
import { PLAYER_ID, type ScreenBox, type ScreenPoint } from '../ui/world-view';
import type { Body } from '../world';
import { framePixel } from '../world/hit';
import {
  CONTACT_ALPHA,
  contactShadow,
  directionFor,
  dropShadow,
  feetOf,
  SHADOW_DEPTH,
  sheetFor,
  tintColour,
  walkTimeScale,
  type CharacterManifest,
  type Figure,
  type IsoTile,
  type Layer,
  type LightingSet,
  type ResidentLight,
  type ShadowMask,
} from '../world/iso';

type Character = {
  sprite: Phaser.GameObjects.Sprite;
  sheet: string;
  contact: Phaser.GameObjects.Image;
  shadows: Map<LightingSet, Phaser.GameObjects.Image>;
  last: Position;
  direction: string;
};

type Assets = {
  characterManifest: CharacterManifest;
  sheetUrl: (image: string) => string | undefined;
  loadImage: (url: string) => Promise<HTMLImageElement>;
};

const MIN_TIME_SCALE = 0.25;
const MAX_TIME_SCALE = 4;
const FIRST_DIRECTION = 'se';
const CONTACT_KEY = 'iso-shadow/contact';

const sheetKey = (id: string) => `iso-character/${id}`;
const animationKey = (sheet: string, name: string, direction: string) => `${sheet}/${name}/${direction}`;
const shadowKey = (set: LightingSet) => `iso-shadow/${set}`;

export class IsoCharacters {
  private readonly scene: Phaser.Scene;
  private readonly tile: IsoTile;
  private readonly manifest: CharacterManifest;
  private readonly sheets: string[];
  private readonly characters = new Map<string, Character>();

  private constructor(scene: Phaser.Scene, tile: IsoTile, manifest: CharacterManifest) {
    this.scene = scene;
    this.tile = tile;
    this.manifest = manifest;
    this.sheets = Object.keys(manifest.characters);
    addMask(scene, CONTACT_KEY, contactShadow(tile));
  }

  static async load(scene: Phaser.Scene, tile: IsoTile, assets: Assets): Promise<IsoCharacters> {
    const manifest = assets.characterManifest;
    const { width: frameWidth, height: frameHeight } = manifest.frame;
    await Promise.all(
      Object.entries(manifest.characters).map(async ([id, { image }]) => {
        const sheet = await assets.loadImage(assets.sheetUrl(image)!);
        scene.textures.addSpriteSheet(sheetKey(id), sheet, { frameWidth, frameHeight });
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
    return new IsoCharacters(scene, tile, manifest);
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
      character.direction = directionFor(step, this.manifest.directions, character.direction);
      character.last = { x, y };
      this.animate(character, body.walking, Math.hypot(step.x, step.y) / dt);

      const figure = figureAt(body.position);
      const light = lightAt(feetOf(body.position));
      character.sprite.setPosition(figure.x, figure.bottom).setDepth(figure.depth);
      character.sprite.setTint(tintColour(light.tint));
      character.contact.setPosition(figure.x, figure.bottom);
      this.shade(character, figure, layers, light.shadows);
    }
    for (const [id, character] of this.characters) {
      if (bodies.has(id)) continue;
      character.sprite.destroy();
      character.contact.destroy();
      for (const shadow of character.shadows.values()) shadow.destroy();
      this.characters.delete(id);
    }
  }

  opaqueAt(id: string, box: ScreenBox, point: ScreenPoint): boolean {
    const sprite = this.characters.get(id)?.sprite;
    if (!sprite) return false;
    const { width, anchor } = this.manifest.frame;
    const { x, y } = framePixel(point, box, { width, height: anchor[1] });
    return (this.scene.textures.getPixelAlpha(x, y, sprite.texture.key, sprite.frame.name) ?? 0) > 0;
  }

  private animate(character: Character, walking: boolean, speed: number): void {
    const { sprite, sheet, direction } = character;
    const key = animationKey(sheet, walking ? 'walk' : 'idle', direction);
    const current = sprite.anims.currentAnim?.key;
    if (current !== key) {
      const stride = walking && current?.startsWith(`${sheet}/walk/`);
      sprite.play({ key, startFrame: stride ? sprite.anims.currentFrame!.index - 1 : 0 });
    }
    if (!walking) sprite.anims.timeScale = 1;
    else if (speed > 0) {
      const scale = walkTimeScale(speed, this.manifest.animations.walk);
      sprite.anims.timeScale = Phaser.Math.Clamp(scale, MIN_TIME_SCALE, MAX_TIME_SCALE);
    }
  }

  private shade(character: Character, figure: Figure, layers: readonly Layer[], alphas: number[]): void {
    for (const shadow of character.shadows.values()) shadow.setVisible(false);
    layers.forEach(({ set }, i) => {
      const shadow = character.shadows.get(set) ?? this.addShadow(character, set);
      shadow.setPosition(figure.x, figure.bottom).setAlpha(alphas[i]).setVisible(alphas[i] > 0);
    });
  }

  private add(id: string, position: Position): Character {
    const sheet = sheetFor(id, this.sheets, PLAYER_ID);
    const { width, height, anchor } = this.manifest.frame;
    const sprite = this.scene.add
      .sprite(0, 0, sheetKey(sheet))
      .setOrigin(anchor[0] / width, anchor[1] / height);
    const contact = this.shadowImage(CONTACT_KEY).setAlpha(CONTACT_ALPHA);
    const character = {
      sprite,
      sheet,
      contact,
      shadows: new Map(),
      last: { ...position },
      direction: FIRST_DIRECTION,
    };
    this.characters.set(id, character);
    return character;
  }

  /** Builds a set's drop shadow while it loads, rather than in the first frame of its fade. */
  prepare(set: LightingSet): void {
    const key = shadowKey(set);
    if (this.scene.textures.exists(key)) return;
    addMask(this.scene, key, dropShadow(this.manifest.sets[set].shadow, this.tile));
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
