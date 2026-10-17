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
  DEFAULT_HOUR,
  figureAt,
  figureBox,
  FIGURE_HEIGHT,
  gridDirection,
  GROUND_DEPTH,
  groundHeights,
  hides,
  isoScroll,
  isoZoom,
  layerAlphas,
  LightMap,
  PAIR_DEPTH,
  residentLight,
  sceneryImages,
  screenAligned,
  SetLoader,
  simClock,
  sliceDraws,
  type Figure,
  type Layer,
  type LightingSet,
  type SceneryManifest,
  type SceneryObject,
  type TiledMapWithTiles,
} from '../world/iso';
import { IsoCharacters } from './iso-characters';

export const ISO_SCENE = 'iso-world';

const KEYS = 'UP,DOWN,LEFT,RIGHT,W,A,S,D';

type Keys = Record<'UP' | 'DOWN' | 'LEFT' | 'RIGHT' | 'W' | 'A' | 'S' | 'D', Phaser.Input.Keyboard.Key>;
type Assets = typeof import('../world/iso/assets');
type Placed = { image: Phaser.GameObjects.Image; depth: number };
/** `rank` is the set's place in the drawn layers, or -1 while it's hidden. */
type SetScenery = {
  manifest: SceneryManifest;
  lightMap: LightMap;
  placed: Placed[];
  objects: Map<string, Placed[]>;
  rank: number;
};
type Geometry = {
  manifest: SceneryManifest;
  heightAt: (position: Position) => number;
  buildings: { object: SceneryObject; cutaway: Cutaway }[];
};

const textureKey = (image: string) => `iso/${image}`;

/** The village in isometric, from A2a's pre-rendered scenery: `world/iso/README.md`. */
export class IsoScene extends Phaser.Scene {
  private readonly collision = CollisionMap.of(village);
  private readonly throttle = new MoveThrottle();
  private readonly sets = new SetLoader(
    (set) => this.loadSet(set),
    (set) => this.unloadSet(set),
  );
  private readonly loaded = new Map<LightingSet, SetScenery>();
  private keys!: Keys;
  private assets?: Assets;
  private charactersLoad?: Promise<IsoCharacters>;
  private characters?: IsoCharacters;
  private geometry?: Geometry;

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
    void this.start();
  }

  update(time: number, delta: number): void {
    if (!this.assets) return;
    const layers = this.sets.update(simClock.hour() ?? DEFAULT_HOUR, simClock.speed);
    const { characters, geometry } = this;
    if (layers.length === 0 || !characters || !geometry) return;
    const dt = Math.min(delta / 1000, MAX_FRAME_SECONDS);
    const player = world.player!;
    player.move(gridDirection(this.direction()), dt, this.collision);
    world.update(dt);

    const position = this.throttle.next(player.position, time / 1000);
    if (position) server.send({ type: 'player_move', position });

    const figure = this.figureAt(player.position);
    this.cutAway(figure, dt);
    this.drawLayers(layers);

    const bodies = new Map<string, Body>([...world.npcs].map(([id, { mover }]) => [id, mover]));
    bodies.set(PLAYER_ID, player);
    const lit = layers.map(({ set, weight }) => ({
      weight,
      light: this.assets!.characterManifest.sets[set],
      lightMap: this.loaded.get(set)!.lightMap,
    }));
    characters.draw(bodies, dt, (at) => this.figureAt(at), layers, (feet) => residentLight(lit, feet));
    this.follow(figure);
  }

  private async start(): Promise<void> {
    await simClock.known(CLOCK_WAIT_MS);
    this.assets = await import('../world/iso/assets');
  }

  private async loadSet(set: LightingSet): Promise<void> {
    const assets = this.assets!;
    const manifest = (await (await fetch(assets.manifestUrl(set)!)).json()) as SceneryManifest;
    this.charactersLoad ??= IsoCharacters.load(this, manifest.tile, assets).then(
      (characters) => (this.characters = characters),
    );
    const images = sceneryImages(manifest);
    const [pixels, sources] = await Promise.all([
      assets.imagePixels(assets.imageUrl(manifest.light_map.image)!),
      Promise.all(images.map((image) => assets.loadImage(assets.imageUrl(image)!))),
      this.charactersLoad,
    ]);
    images.forEach((image, i) => this.textures.addImage(textureKey(image), sources[i]));
    this.loaded.set(set, this.placeSet(manifest, new LightMap(manifest.light_map, pixels)));
    this.geometry ??= {
      manifest,
      heightAt: groundHeights(village as TiledMapWithTiles, manifest.ground.heights),
      buildings: manifest.objects
        .filter(({ kind }) => kind === 'building')
        .map((object) => ({ object, cutaway: new Cutaway() })),
    };
  }

  private placeSet(manifest: SceneryManifest, lightMap: LightMap): SetScenery {
    const place = (x: number, y: number, image: string, depth: number): Placed => ({
      image: this.add.image(x, y, textureKey(image)).setOrigin(0).setDepth(depth).setVisible(false),
      depth,
    });
    const ground = manifest.ground.chunks.map(({ image, x, y }) => place(x, y, image, GROUND_DEPTH));
    const objects = new Map(
      manifest.objects.map((object) => {
        const slices = sliceDraws(object, manifest.tile).map(({ x, y, cropX, cropWidth, depth }) => {
          const slice = place(x, y, object.image, depth);
          slice.image.setCrop(cropX, 0, cropWidth, object.height);
          return slice;
        });
        return [object.id, slices];
      }),
    );
    const placed = [...ground, ...[...objects.values()].flat()];
    return { manifest, lightMap, placed, objects, rank: -1 };
  }

  private unloadSet(set: LightingSet): void {
    const scenery = this.loaded.get(set);
    if (!scenery) return;
    this.loaded.delete(set);
    for (const { image } of scenery.placed) image.destroy();
    for (const image of sceneryImages(scenery.manifest)) this.textures.remove(textureKey(image));
  }

  private drawLayers(layers: readonly Layer[]): void {
    const open = layerAlphas(layers);
    for (const [set, scenery] of this.loaded) {
      const rank = layers.findIndex((layer) => layer.set === set);
      if (rank !== scenery.rank) {
        scenery.rank = rank;
        for (const { image, depth } of scenery.placed) {
          image.setVisible(rank >= 0).setDepth(depth + Math.max(rank, 0) * PAIR_DEPTH);
        }
      }
      if (rank < 0) continue;
      for (const { image } of scenery.placed) image.setAlpha(open[rank]);
      for (const { object, cutaway } of this.geometry!.buildings) {
        if (cutaway.alpha === 1) continue;
        const faded = layerAlphas(layers, cutaway.alpha)[rank];
        for (const { image } of scenery.objects.get(object.id) ?? []) image.setAlpha(faded);
      }
    }
  }

  private figureAt(position: Position): Figure {
    const { manifest, heightAt } = this.geometry!;
    return figureAt(position, manifest.tile, heightAt);
  }

  private spriteOf(id: string): ScreenSprite | undefined {
    const position = world.positionOf(id);
    const characters = this.characters;
    if (!this.geometry || !characters || !position) return undefined;
    const figure = this.figureAt(position);
    const box = figureBox(figure, this.cameras.main);
    return { box, depth: figure.depth, opaqueAt: (point) => characters.opaqueAt(id, box, point) };
  }

  private cutAway(player: Figure, dt: number): void {
    const { manifest, buildings } = this.geometry!;
    for (const { object, cutaway } of buildings) {
      cutaway.update(hides(object, player, manifest.tile), dt);
    }
  }

  private follow(player: Figure): void {
    const { manifest } = this.geometry!;
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
