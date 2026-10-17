import Phaser from 'phaser';
import { setPositionProvider } from '../audio';
import { server, type Position } from '../net';
import { PLAYER_ID, setWorldView, type ScreenSprite, type WorldView } from '../ui/world-view';
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
  Cutaway,
  figureAt,
  figureBox,
  FIGURE_HEIGHT,
  gridDirection,
  GROUND_DEPTH,
  groundHeights,
  hides,
  isoScroll,
  isoZoom,
  lightingSetAt,
  sceneryImages,
  screenAligned,
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
type Building = { object: SceneryObject; slices: Phaser.GameObjects.Image[]; cutaway: Cutaway };
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
    this.cameras.main.setRoundPixels(true);
    this.keys = this.input.keyboard!.addKeys(KEYS, false) as Keys;
    world.spawnPlayer(entryOf(village, 'square') ?? { x: village.width / 2, y: village.height / 2 });

    const view: WorldView = {
      positionOf: (id) => world.positionOf(id),
      npcIds: () => world.npcs.keys(),
      bubbleAnchor: (id) => {
        const box = this.spriteOf(id)?.box;
        return box && { x: box.x + box.width / 2, y: box.y };
      },
      spriteOf: (id) => this.spriteOf(id),
    };
    const cleanups = [
      setWorldView(view),
      setPositionProvider({
        positionOf: (id) => screenAligned(world.positionOf(id)),
        listenerPosition: () => screenAligned(world.player?.position),
      }),
      server.on('snapshot', () => this.throttle.forget()),
    ];
    this.events.once(Phaser.Scenes.Events.SHUTDOWN, () => cleanups.forEach((cleanup) => cleanup()));
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
    const { imageUrl, manifestUrl } = await import('../world/iso/assets');
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
      if (object.kind === 'building') buildings.push({ object, slices, cutaway: new Cutaway() });
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
    return figureAt(position, manifest.tile, heightAt);
  }

  private spriteOf(id: string): ScreenSprite | undefined {
    const position = world.positionOf(id);
    if (!this.scenery || !position) return undefined;
    const figure = this.figureAt(position);
    const box = figureBox(figure, this.cameras.main);
    const { characters } = this.scenery;
    return { box, depth: figure.depth, opaqueAt: (point) => characters.opaqueAt(id, box, point) };
  }

  private cutAway(player: Figure, dt: number): void {
    const { manifest, buildings } = this.scenery!;
    for (const { object, slices, cutaway } of buildings) {
      const before = cutaway.alpha;
      const alpha = cutaway.update(hides(object, player, manifest.tile), dt);
      if (alpha !== before) for (const slice of slices) slice.setAlpha(alpha);
    }
  }

  private follow(player: Figure): void {
    const { manifest } = this.scenery!;
    const camera = this.cameras.main;
    const zoom = isoZoom(camera.width, window.devicePixelRatio, manifest.tile);
    if (zoom !== camera.zoom) camera.setZoom(zoom);
    const target = { x: player.x, y: player.bottom - FIGURE_HEIGHT / 2 };
    const scroll = isoScroll(target, camera, manifest.map, manifest.tile, zoom);
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
