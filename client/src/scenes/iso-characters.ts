import Phaser from 'phaser';
import type { Position } from '../net';
import { PLAYER_ID, type ScreenBox, type ScreenPoint } from '../ui/world-view';
import {
  characterFor,
  characterKeys,
  facingFor,
  PLAYER_SPEED,
  poseOf,
  WALKING_SPEED,
  type Body,
  type Facing,
} from '../world';
import { framePixel } from '../world/hit';
import { PLACEHOLDER_SCALE, project, type Figure, type IsoTile } from '../world/iso';

type Character = { sprite: Phaser.GameObjects.Sprite; last: Position; facing: Facing };

/** Residents and the player, drawn with today's top-down atlases until A2b's iso sprites land. */
export class IsoCharacters {
  private readonly scene: Phaser.Scene;
  private readonly tile: IsoTile;
  private readonly characters = new Map<string, Character>();

  constructor(scene: Phaser.Scene, tile: IsoTile) {
    this.scene = scene;
    this.tile = tile;
  }

  draw(bodies: ReadonlyMap<string, Body>, figureAt: (position: Position) => Figure): void {
    for (const [id, body] of bodies) {
      const character = this.characters.get(id) ?? this.add(id, body.position);
      const figure = figureAt(body.position);
      character.sprite.setPosition(figure.x, figure.bottom).setDepth(figure.depth);
      const { x, y } = body.position;
      const step = project(this.tile, { x: x - character.last.x, y: y - character.last.y });
      character.facing = facingFor(step.x, step.y, character.facing);
      character.last = { x, y };
      const pose = poseOf(character.sprite.texture.key, { ...body, facing: character.facing });
      if ('animation' in pose) character.sprite.play(pose.animation, true);
      else character.sprite.stop().setFrame(pose.frame);
    }
    for (const [id, { sprite }] of this.characters) {
      if (bodies.has(id)) continue;
      sprite.destroy();
      this.characters.delete(id);
    }
  }

  opaqueAt(id: string, box: ScreenBox, point: ScreenPoint): boolean {
    const sprite = this.characters.get(id)?.sprite;
    if (!sprite) return false;
    const { x, y } = framePixel(point, box, sprite.frame);
    return (this.scene.textures.getPixelAlpha(x, y, sprite.texture.key, sprite.frame.name) ?? 0) > 0;
  }

  private add(id: string, position: Position): Character {
    const sprite = this.scene.add
      .sprite(0, 0, characterFor(id, characterKeys))
      .setOrigin(0.5, 1)
      .setScale(PLACEHOLDER_SCALE);
    if (id === PLAYER_ID) sprite.anims.timeScale = PLAYER_SPEED / WALKING_SPEED;
    const character = { sprite, last: { ...position }, facing: 'down' as Facing };
    this.characters.set(id, character);
    return character;
  }
}
