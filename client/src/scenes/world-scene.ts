import Phaser from 'phaser';
import { setPositionProvider } from '../audio';
import { server } from '../net';
import { PLAYER_ID, setWorldView, type ScreenPoint } from '../ui/world-view';
import {
  characterFor,
  characterKeys,
  CollisionMap,
  entryOf,
  feetOf,
  followScroll,
  MAP_KEY,
  MAX_FRAME_SECONDS,
  MoveThrottle,
  PLAYER_SPEED,
  poseOf,
  SPRITE_HEIGHT,
  TILE_SIZE,
  TILES_KEY,
  TILESET,
  toCanvas,
  village,
  WALKING_SPEED,
  world,
  ZOOM,
  type Body,
  type Direction,
  type Point,
} from '../world';

export const WORLD_SCENE = 'world';

const LAYERS_BELOW = ['ground', 'buildings', 'decor'];
const LAYER_ABOVE = 'above';
const KEYS = 'UP,DOWN,LEFT,RIGHT,W,A,S,D';
const WORLD_SIZE = { width: village.width * TILE_SIZE, height: village.height * TILE_SIZE };

type Keys = Record<'UP' | 'DOWN' | 'LEFT' | 'RIGHT' | 'W' | 'A' | 'S' | 'D', Phaser.Input.Keyboard.Key>;

export class WorldScene extends Phaser.Scene {
  private readonly collision = CollisionMap.of(village);
  private readonly throttle = new MoveThrottle();
  private readonly sprites = new Map<string, Phaser.GameObjects.Sprite>();
  private keys!: Keys;
  private scroll: Point = { x: 0, y: 0 };

  constructor() {
    super(WORLD_SCENE);
  }

  create(): void {
    const map = this.make.tilemap({ key: MAP_KEY });
    const tiles = map.addTilesetImage(TILESET, TILES_KEY)!;
    for (const name of LAYERS_BELOW) map.createLayer(name, tiles);
    map.createLayer(LAYER_ABOVE, tiles)!.setDepth(WORLD_SIZE.height + SPRITE_HEIGHT);

    this.cameras.main.setZoom(ZOOM).setRoundPixels(true);
    this.keys = this.input.keyboard!.addKeys(KEYS, false) as Keys;
    world.spawnPlayer(entryOf(village, 'square') ?? { x: village.width / 2, y: village.height / 2 });

    const view = {
      positionOf: (id: string) => world.positionOf(id),
      npcIds: () => world.npcs.keys(),
      bubbleAnchor: (id: string) => this.bubbleAnchor(id),
      listenerPosition: () => world.player?.position,
    };
    const cleanups = [
      setWorldView(view),
      setPositionProvider(view),
      server.on('snapshot', () => this.throttle.forget()),
    ];
    this.events.once(Phaser.Scenes.Events.SHUTDOWN, () => cleanups.forEach((cleanup) => cleanup()));
  }

  update(time: number, delta: number): void {
    const dt = Math.min(delta / 1000, MAX_FRAME_SECONDS);
    const player = world.player!;
    player.move(this.direction(), dt, this.collision);
    world.update(dt);

    const position = this.throttle.next(player.position, time / 1000);
    if (position) server.send({ type: 'player_move', position });

    this.drawBodies();
    const feet = feetOf(player.position);
    this.scroll = followScroll(
      { x: feet.x, y: feet.y - SPRITE_HEIGHT / 2 },
      this.cameras.main,
      WORLD_SIZE,
      ZOOM,
    );
    this.cameras.main.setScroll(this.scroll.x, this.scroll.y);
  }

  private direction(): Direction {
    const down = (...keys: (keyof Keys)[]) => (keys.some((key) => this.keys[key].isDown) ? 1 : 0);
    return {
      x: down('RIGHT', 'D') - down('LEFT', 'A'),
      y: down('DOWN', 'S') - down('UP', 'W'),
    };
  }

  private drawBodies(): void {
    const bodies = new Map<string, Body>([...world.npcs].map(([id, { mover }]) => [id, mover]));
    if (world.player) bodies.set(PLAYER_ID, world.player);
    for (const [id, body] of bodies) {
      const sprite = this.sprites.get(id) ?? this.addSprite(id);
      const feet = feetOf(body.position);
      sprite.setPosition(feet.x, feet.y).setDepth(feet.y);
      const pose = poseOf(sprite.texture.key, body);
      if ('animation' in pose) {
        sprite.play(pose.animation, true);
      } else {
        sprite.stop().setFrame(pose.frame);
      }
    }
    for (const [id, sprite] of this.sprites) {
      if (bodies.has(id)) continue;
      sprite.destroy();
      this.sprites.delete(id);
    }
  }

  private addSprite(id: string): Phaser.GameObjects.Sprite {
    const sprite = this.add.sprite(0, 0, characterFor(id, characterKeys)).setOrigin(0.5, 1);
    if (id === PLAYER_ID) sprite.anims.timeScale = PLAYER_SPEED / WALKING_SPEED;
    this.sprites.set(id, sprite);
    return sprite;
  }

  private bubbleAnchor(id: string): ScreenPoint | undefined {
    const position = world.positionOf(id);
    if (!position) return undefined;
    const feet = feetOf(position);
    return toCanvas({ x: feet.x, y: feet.y - SPRITE_HEIGHT }, this.scroll, this.cameras.main, ZOOM);
  }
}
