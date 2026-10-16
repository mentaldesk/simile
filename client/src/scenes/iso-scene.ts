import Phaser from 'phaser';
import { server, type Position } from '../net';
import { PLAYER_ID } from '../ui/world-view';
import {
  CollisionMap,
  entryOf,
  MAX_FRAME_SECONDS,
  MoveThrottle,
  village,
  world,
  type Body,
  type Direction,
} from '../world';
import {
  CLOCK_WAIT_MS,
  CUTAWAY_ALPHA,
  fade,
  feetOf,
  FIGURE_HEIGHT,
  gridDirection,
  GROUND_DEPTH,
  groundHeights,
  hides,
  imageUrl,
  ISO_ZOOM,
  isoScroll,
  lightingSetAt,
  manifestUrl,
  project,
  residentDepth,
  sceneryImages,
  simClock,
  sliceDraws,
  type Figure,
  type SceneryManifest,
  type SceneryObject,
  type TiledMapWithTiles,
} from '../world/iso';
import { IsoCharacters } from './iso-characters';

export const ISO_SCENE = 'iso-world';

const KEYS = 'UP,DOWN,LEFT,RIGHT,W,A,S,D';

type Keys = Record<'UP' | 'DOWN' | 'LEFT' | 'RIGHT' | 'W' | 'A' | 'S' | 'D', Phaser.Input.Keyboard.Key>;
type Building = { object: SceneryObject; slices: Phaser.GameObjects.Image[]; alpha: number };
type Scenery = {
  manifest: SceneryManifest;
  buildings: Building[];
  characters: IsoCharacters;
  heightAt: (position: Position) => number;
};

const textureKey = (image: string) => `iso/${image}`;

/** The village in isometric, from A2a's pre-rendered scenery: `world/iso/README.md`. */
export class IsoScene extends Phaser.Scene {
  private readonly collision = CollisionMap.of(village);
  private readonly throttle = new MoveThrottle();
  private keys!: Keys;
  private scenery?: Scenery;

  constructor() {
    super(ISO_SCENE);
  }

  create(): void {
    this.cameras.main.setZoom(ISO_ZOOM).setRoundPixels(true);
    this.keys = this.input.keyboard!.addKeys(KEYS, false) as Keys;
    world.spawnPlayer(entryOf(village, 'square') ?? { x: village.width / 2, y: village.height / 2 });
    const unsubscribe = server.on('snapshot', () => this.throttle.forget());
    this.events.once(Phaser.Scenes.Events.SHUTDOWN, unsubscribe);
    void this.loadScenery();
  }

  update(time: number, delta: number): void {
    if (!this.scenery) return;
    const dt = Math.min(delta / 1000, MAX_FRAME_SECONDS);
    const player = world.player!;
    player.move(gridDirection(this.direction()), dt, this.collision);
    world.update(dt);

    const position = this.throttle.next(player.position, time / 1000);
    if (position) server.send({ type: 'player_move', position });

    const bodies = new Map<string, Body>([...world.npcs].map(([id, { mover }]) => [id, mover]));
    bodies.set(PLAYER_ID, player);
    this.scenery.characters.draw(bodies, (at) => this.figureAt(at));

    const figure = this.figureAt(player.position);
    this.cutAway(figure, dt);
    this.follow(figure);
  }

  private async loadScenery(): Promise<void> {
    const set = lightingSetAt(await simClock.known(CLOCK_WAIT_MS));
    const key = `iso/${set}`;
    this.load.json(key, manifestUrl(set));
    await this.loadQueued();
    const manifest = this.cache.json.get(key) as SceneryManifest;
    for (const image of sceneryImages(manifest)) this.load.image(textureKey(image), imageUrl(image));
    await this.loadQueued();
    this.drawScenery(manifest);
  }

  private loadQueued(): Promise<void> {
    return new Promise((resolve) => {
      this.load.once(Phaser.Loader.Events.COMPLETE, () => resolve());
      this.load.start();
    });
  }

  private drawScenery(manifest: SceneryManifest): void {
    for (const { image, x, y } of manifest.ground.chunks) {
      this.add.image(x, y, textureKey(image)).setOrigin(0).setDepth(GROUND_DEPTH);
    }
    const buildings: Building[] = [];
    for (const object of manifest.objects) {
      const slices = sliceDraws(object, manifest.tile).map(({ x, y, cropX, cropWidth, depth }) =>
        this.add
          .image(x, y, textureKey(object.image))
          .setOrigin(0)
          .setCrop(cropX, 0, cropWidth, object.height)
          .setDepth(depth),
      );
      if (object.kind === 'building') buildings.push({ object, slices, alpha: 1 });
    }
    this.scenery = {
      manifest,
      buildings,
      characters: new IsoCharacters(this, manifest.tile),
      heightAt: groundHeights(village as TiledMapWithTiles, manifest.ground.heights),
    };
  }

  private figureAt(position: Position): Figure {
    const { manifest, heightAt } = this.scenery!;
    const feet = feetOf(position);
    const screen = project(manifest.tile, feet, heightAt(position));
    return {
      x: screen.x,
      top: screen.y - FIGURE_HEIGHT,
      bottom: screen.y,
      depth: residentDepth(feet, manifest.tile),
    };
  }

  private cutAway(player: Figure, dt: number): void {
    const { manifest, buildings } = this.scenery!;
    for (const building of buildings) {
      const target = hides(building.object, player, manifest.tile) ? CUTAWAY_ALPHA : 1;
      if (building.alpha === target) continue;
      building.alpha = fade(building.alpha, target, dt);
      for (const slice of building.slices) slice.setAlpha(building.alpha);
    }
  }

  private follow(player: Figure): void {
    const { manifest } = this.scenery!;
    const camera = this.cameras.main;
    const target = { x: player.x, y: player.bottom - FIGURE_HEIGHT / 2 };
    const scroll = isoScroll(target, camera, manifest.map, manifest.tile, ISO_ZOOM);
    camera.setScroll(scroll.x, scroll.y);
  }

  private direction(): Direction {
    const down = (...keys: (keyof Keys)[]) => (keys.some((key) => this.keys[key].isDown) ? 1 : 0);
    return {
      x: down('RIGHT', 'D') - down('LEFT', 'A'),
      y: down('DOWN', 'S') - down('UP', 'W'),
    };
  }
}
