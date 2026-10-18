import Phaser from 'phaser';
import type { Position } from '../net';
import type { ScreenBox, ScreenPoint } from '../ui/world-view';
import { characterFor, characterKeys, WALK_FPS, type Body, type Point } from '../world';
import { framePixel } from '../world/hit';
import {
  CONTACT_ALPHA,
  contactShadow,
  dropShadow,
  facingFor,
  feetOf,
  Idle,
  ISO_FACINGS,
  isoWalkFrames,
  PIXEL_SCALE,
  pixelFrame,
  SHADOW_DEPTH,
  standingFrame,
  stillFor,
  tintColour,
  walkTimeScale,
  type Figure,
  type IsoFacing,
  type IsoTile,
  type ResidentLight,
  type Seat,
  type Still,
  type SceneSet,
  type SetLight,
  type ShadowMask,
  type SpriteFrame,
} from '../world/iso';

/** Where the characters' sprites come from: `pixelArt` is A1's sprites. */
export interface CharacterArt {
  /** Every character's, as drawn, in scene px. */
  readonly frame: SpriteFrame;
  load(scene: Phaser.Scene): Promise<void>;
  add(scene: Phaser.Scene, id: string): Puppet;
}

/** A character's sprite, with its origin at the feet. */
export type Puppet = {
  sprite: Phaser.GameObjects.Sprite;
  /** After a step on the map, at `speed` tiles a second. */
  pose(step: Point, walking: boolean, speed: number): void;
  /** Still, on one of A1's frames, facing that way. */
  hold(frame: string, facing: IsoFacing): void;
  readonly facing: IsoFacing;
};

/** What keeping still depends on: where seats are and who's talking. */
export type Surroundings = {
  seatAt(position: Position): Seat | undefined;
  talking(id: string): boolean;
};

type Character = {
  puppet: Puppet;
  contact: Phaser.GameObjects.Image;
  shadows: Map<SceneSet, Phaser.GameObjects.Image>;
  last: Position;
  idle: Idle;
};

const CONTACT_KEY = 'iso-shadow/contact';
const shadowKey = (set: SceneSet) => `iso-shadow/${set}`;

type Lit = { set: SceneSet };

/** Draws characters from any `CharacterArt`, lit and shadowed by the sets they stand in. */
export class IsoCharacters {
  readonly frame: SpriteFrame;
  private readonly scene: Phaser.Scene;
  private readonly tile: IsoTile;
  private readonly art: CharacterArt;
  private readonly lights: Record<SceneSet, SetLight>;
  private readonly characters = new Map<string, Character>();

  private constructor(
    scene: Phaser.Scene,
    tile: IsoTile,
    art: CharacterArt,
    lights: Record<SceneSet, SetLight>,
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
    lights: Record<SceneSet, SetLight>,
  ): Promise<IsoCharacters> {
    await art.load(scene);
    return new IsoCharacters(scene, tile, art, lights);
  }

  draw(
    bodies: ReadonlyMap<string, Body>,
    dt: number,
    figureAt: (position: Position) => Figure,
    layers: readonly Lit[],
    lightAt: (feet: Position) => ResidentLight,
    surroundings: Surroundings,
  ): void {
    const positions = new Map([...bodies].map(([id, { position }]) => [id, position]));
    for (const [id, body] of bodies) {
      const character = this.characters.get(id) ?? this.add(id, body.position);
      const { x, y } = body.position;
      const step = { x: x - character.last.x, y: y - character.last.y };
      character.last = { x, y };
      const still = this.keepStill(id, body, character, dt, positions, surroundings);
      if (!still) character.puppet.pose(step, true, Math.hypot(step.x, step.y) / dt);

      const at = still ? { x: x + still.seat.x, y: y + still.seat.y } : body.position;
      const figure = figureAt(at);
      const depth = still?.nearer ? figureAt({ x: at.x + still.nearer, y: at.y + still.nearer }).depth : figure.depth;
      const light = lightAt(feetOf(at));
      const lift = (still?.seat.z ?? 0) * this.tile.px_per_metre_up;
      const { sprite } = character.puppet;
      sprite.setPosition(figure.x, figure.bottom - lift).setDepth(depth).setTint(tintColour(light.tint));
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

  arrive(id: string, position: Position, facing: Point): void {
    const character = this.characters.get(id);
    if (!character) return;
    character.last = { ...position };
    character.puppet.pose(facing, false, 0);
  }

  /** Still: their pose or idling, and where they're drawn. Undefined while they walk. */
  private keepStill(
    id: string,
    body: Body,
    { puppet, idle }: Character,
    dt: number,
    positions: ReadonlyMap<string, Position>,
    surroundings: Surroundings,
  ): Still | undefined {
    if (body.walking) {
      idle.reset();
      return undefined;
    }
    idle.update(dt);
    const server = body.pose !== undefined;
    const toward = server ? idle.towards(id, body.position, positions, surroundings.talking) : undefined;
    const seat = server ? surroundings.seatAt(body.position) : undefined;
    const still = stillFor(body, puppet.facing, idle.shifted, seat, toward);
    puppet.hold(still.frame, still.facing);
    return still;
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
  prepare(set: SceneSet): void {
    const key = shadowKey(set);
    if (this.scene.textures.exists(key)) return;
    addMask(this.scene, key, dropShadow(this.lights[set].shadow, this.tile));
  }

  private shade(character: Character, figure: Figure, layers: readonly Lit[], alphas: number[]): void {
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
      idle: new Idle(),
    };
    this.characters.set(id, character);
    return character;
  }

  private addShadow(character: Character, set: SceneSet): Phaser.GameObjects.Image {
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
const FIRST_FACING: IsoFacing = 'down';

const walkKey = (key: string, facing: IsoFacing) => `iso-walk/${key}/${facing}`;

/** A1's sprites, which `BootScene` loads, at `scale` scene px to a texture px. */
export function pixelArt(scale = PIXEL_SCALE): CharacterArt {
  const frame = pixelFrame(scale);

  const load = async (scene: Phaser.Scene) => {
    for (const key of characterKeys) {
      scene.textures.get(key).setFilter(Phaser.Textures.FilterMode.NEAREST);
      for (const facing of ISO_FACINGS) {
        if (scene.anims.exists(walkKey(key, facing))) continue;
        scene.anims.create({
          key: walkKey(key, facing),
          frames: isoWalkFrames(facing).map((name) => ({ key, frame: name })),
          frameRate: WALK_FPS,
          repeat: -1,
        });
      }
    }
  };

  const add = (scene: Phaser.Scene, id: string): Puppet => {
    const key = characterFor(id, characterKeys);
    let facing = FIRST_FACING;
    const sprite = scene.add.sprite(0, 0, key, standingFrame(facing)).setOrigin(0.5, 1).setScale(scale);
    const pose = (step: Point, walking: boolean, speed: number) => {
      facing = facingFor(step, facing);
      if (!walking) {
        sprite.stop().setFrame(standingFrame(facing));
        return;
      }
      const animation = walkKey(key, facing);
      const { anims } = sprite;
      if (!anims.isPlaying) sprite.play(animation);
      else if (anims.currentAnim?.key !== animation) {
        sprite.play({ key: animation, startFrame: anims.currentFrame!.index - 1 });
      }
      if (speed > 0) anims.timeScale = Phaser.Math.Clamp(walkTimeScale(speed), MIN_TIME_SCALE, MAX_TIME_SCALE);
    };
    const hold = (frame: string, next: IsoFacing) => {
      facing = next;
      if (sprite.anims.isPlaying) sprite.stop();
      if (sprite.frame.name !== frame) sprite.setFrame(frame);
    };
    return {
      sprite,
      pose,
      hold,
      get facing() {
        return facing;
      },
    };
  };

  return { frame, load, add };
}
