import Phaser from 'phaser';
import { setPositionProvider } from '../audio';
import { server, type Position } from '../net';
import { PLAYER_ID, setWorldView, type ScreenSprite, type WorldView } from '../ui/world-view';
import {
  CollisionMap,
  Doorways,
  doorsOn,
  entryOf,
  interactables,
  loadMap,
  mapIds,
  maps,
  MAX_FRAME_SECONDS,
  MoveThrottle,
  village,
  VILLAGE,
  world,
  type Body,
  type Direction,
  type TiledMap,
} from '../world';
import {
  CLOCK_WAIT_MS,
  Cutaway,
  cutawaysOf,
  DEFAULT_HOUR,
  figureAt,
  figureBox,
  gridDirection,
  GROUND_DEPTH,
  groundHeights,
  hides,
  INSIDE,
  INSIDE_SUN,
  insideLight,
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
  UPLOAD_MS_PER_FRAME,
  Uploads,
  type Figure,
  type Layer,
  type LightingSet,
  type SceneryManifest,
  type SceneryObject,
  type SceneSet,
  type SetLight,
  type TiledMapWithTiles,
} from '../world/iso';
import {
  cropPixels,
  IsoMurals,
  muralWalls,
  setMuralView,
  skewed,
  type Box,
  type Pixels,
} from '../world/iso/murals';
import { IsoCharacters, pixelArt } from './iso-characters';

export const ISO_SCENE = 'iso-world';

const KEYS = 'UP,DOWN,LEFT,RIGHT,W,A,S,D';
const FADE_DEPTH = 1e9;
const INTERIOR_BACKGROUND = '#0b0a09';

type Keys = Record<'UP' | 'DOWN' | 'LEFT' | 'RIGHT' | 'W' | 'A' | 'S' | 'D', Phaser.Input.Keyboard.Key>;
type Assets = typeof import('../world/iso/assets');
type Placed = { image: Phaser.GameObjects.Image; depth: number };
/** One manifest's scenery. `rank` is its place in the drawn layers, or -1 while it's hidden. */
type Scenery = {
  manifest: SceneryManifest;
  lightMap: LightMap;
  bitmaps: ImageBitmap[];
  textures: string;
  placed: Placed[];
  objects: Map<string, Placed[]>;
  rank: number;
};
type Interior = Scenery | 'loading';
type Drawn = { scenery: Scenery; set: SceneSet; weight: number };
type Geometry = {
  manifest: SceneryManifest;
  heightAt: (position: Position) => number;
  buildings: { object: SceneryObject; cutaway: Cutaway }[];
};

const collisions = new Map<string, CollisionMap>();
const collisionOf = (map: string): CollisionMap | undefined => {
  const tiled = maps[map];
  if (tiled && !collisions.has(map)) collisions.set(map, CollisionMap.of(tiled));
  return collisions.get(map);
};
const square = {
  ...(entryOf(village, 'square') ?? { x: village.width / 2, y: village.height / 2 }),
  map: VILLAGE,
};

function geometryOf(manifest: SceneryManifest, map: TiledMap): Geometry {
  return {
    manifest,
    heightAt: groundHeights(map as TiledMapWithTiles, manifest.ground.heights),
    buildings: cutawaysOf(manifest.objects).map((object) => ({ object, cutaway: new Cutaway() })),
  };
}

/** The village and its interiors in isometric, from the pre-rendered scenery: `world/iso/README.md`. */
export class IsoScene extends Phaser.Scene {
  private readonly throttle = new MoveThrottle();
  private readonly doorways = new Doorways();
  private readonly sets = new SetLoader(
    (set) => this.loadSet(set),
    (set) => this.unloadSet(set),
  );
  private readonly loaded = new Map<LightingSet, Scenery>();
  private readonly interiors = new Map<string, Interior>();
  private readonly geometries = new Map<string, Geometry>();
  private readonly uploads = new Uploads();
  private keys!: Keys;
  private fade!: Phaser.GameObjects.Rectangle;
  private assets?: Assets;
  private residentLights?: Record<SceneSet, SetLight>;
  private charactersLoad?: Promise<IsoCharacters>;
  private characters?: IsoCharacters;
  private murals?: IsoMurals<ImageBitmap>;
  private shown?: string;

  constructor() {
    super(ISO_SCENE);
  }

  create(): void {
    this.cameras.main.setRoundPixels(true);
    this.keys = this.input.keyboard!.addKeys(KEYS, false) as Keys;
    this.fade = this.add.rectangle(0, 0, 1, 1, 0x000000).setOrigin(0).setScrollFactor(0).setDepth(FADE_DEPTH);
    world.spawnPlayer(square);

    const view: WorldView = {
      positionOf: (id) => world.positionOf(id),
      npcIds: () => [...world.here()].map(({ id }) => id),
      bubbleAnchor: (id) => {
        const box = this.spriteOf(id)?.box;
        return box && { x: box.x + box.width / 2, y: box.y };
      },
      spriteOf: (id) => this.spriteOf(id),
    };
    const cleanups = [
      setWorldView(view),
      setPositionProvider({
        positionOf: (id) => screenAligned(world.whereIs(id)),
        listenerPosition: () => screenAligned(world.player?.position),
      }),
      server.on('snapshot', () => this.throttle.forget()),
      setMuralView({
        wallAt: ({ x, y }) =>
          world.map === VILLAGE ? this.murals?.wallAt(this.cameras.main.getWorldPoint(x, y)) : undefined,
      }),
      () => this.murals?.destroy(),
      () => interactables.update(undefined),
    ];
    this.events.once(Phaser.Scenes.Events.SHUTDOWN, () => cleanups.forEach((cleanup) => cleanup()));
    void this.start();
  }

  update(time: number, delta: number): void {
    if (!this.assets) return;
    this.uploads.run(UPLOAD_MS_PER_FRAME);
    const villageLayers = this.sets.update(simClock.hour() ?? DEFAULT_HOUR, simClock.speed);
    const player = world.player!;
    if (!mapIds.includes(player.map)) player.place(square);
    const dt = Math.min(delta / 1000, MAX_FRAME_SECONDS);
    const direction = gridDirection(this.direction());
    const arrival = this.doorways.update(player.position, direction, dt, (map) => this.ready(map));
    if (arrival) {
      player.place(arrival.position);
      this.characters?.arrive(PLAYER_ID, arrival.position, arrival.facing);
    }
    this.coverFade();

    const map = player.map;
    const drawn = this.drawnOn(map, villageLayers);
    const geometry = this.geometries.get(map);
    const collision = collisionOf(map);
    const { characters, residentLights } = this;
    if (drawn.length === 0 || !characters || !residentLights || !geometry || !collision) {
      if (map !== VILLAGE) this.requestInterior(map);
      return;
    }
    if (this.doorways.holding) player.walking = false;
    else player.move(direction, dt, collision);
    world.update(dt);
    interactables.update(player.position);

    const position = this.throttle.next(player.position, time / 1000);
    if (position) server.send({ type: 'player_move', position });

    const figure = this.figureAt(player.position, geometry);
    this.cutAway(figure, dt, geometry);
    this.drawLayers(drawn, geometry);
    this.show(map);

    const bodies = new Map<string, Body>([...world.here()].map(({ id, mover }) => [id, mover]));
    bodies.set(PLAYER_ID, player);
    const lit = drawn.map(({ scenery, set, weight }) => ({
      weight,
      light: residentLights[set],
      lightMap: scenery.lightMap,
    }));
    const at = (position: Position) => this.figureAt(position, geometry);
    characters.draw(bodies, dt, at, drawn, (feet) => residentLight(lit, feet));
    this.drawMurals(dt, villageLayers, map === VILLAGE ? geometry : undefined);
    this.follow(figure, geometry);
  }

  private async start(): Promise<void> {
    await simClock.known(CLOCK_WAIT_MS);
    this.assets = await import('../world/iso/assets');
  }

  /** Whether the map can be drawn, starting its scenery loading if it hasn't. */
  private ready(map: string): boolean {
    if (map === VILLAGE) return this.geometries.has(VILLAGE) && this.sets.layers.length > 0;
    this.requestInterior(map);
    return typeof this.interiors.get(map) === 'object';
  }

  private drawnOn(map: string, villageLayers: readonly Layer[]): Drawn[] {
    if (map === VILLAGE) {
      return villageLayers.map(({ set, weight }) => ({ scenery: this.loaded.get(set)!, set, weight }));
    }
    const interior = this.interiors.get(map);
    return typeof interior === 'object' ? [{ scenery: interior, set: INSIDE, weight: 1 }] : [];
  }

  private coverFade(): void {
    const { width, height } = this.cameras.main;
    const { black } = this.doorways;
    this.fade.setSize(width, height).setAlpha(black).setVisible(black > 0);
  }

  /** Once a map is drawn: the dark around an interior, and the interiors its doors lead to. */
  private show(map: string): void {
    if (map === this.shown) return;
    this.shown = map;
    const camera = this.cameras.main;
    if (map === VILLAGE) camera.setBackgroundColor();
    else camera.setBackgroundColor(INTERIOR_BACKGROUND);
    for (const { to } of doorsOn(map)) if (to.map !== VILLAGE) this.requestInterior(to.map);
  }

  private requestInterior(map: string): void {
    if (this.interiors.has(map) || !this.assets?.interiorManifestUrl(map)) return;
    this.interiors.set(map, 'loading');
    this.loadInterior(map).then(
      (scenery) => this.interiors.set(map, scenery),
      (error: unknown) => {
        console.error(`Couldn't load the ${map} interior`, error);
        this.interiors.delete(map);
      },
    );
  }

  private async loadInterior(map: string): Promise<Scenery> {
    const assets = this.assets!;
    const [manifest, tiled] = await Promise.all([fetchManifest(assets.interiorManifestUrl(map)!), loadMap(map)]);
    const scenery = await this.loadScenery(manifest, INSIDE, 'iso/interiors/', assets.interiorImageUrl);
    this.geometries.set(map, geometryOf(manifest, tiled));
    return scenery;
  }

  private async loadSet(set: LightingSet): Promise<void> {
    const assets = this.assets!;
    const manifest = await fetchManifest(assets.manifestUrl(set)!);
    const scenery = await this.loadScenery(manifest, set, 'iso/', assets.imageUrl);
    this.loaded.set(set, scenery);
    if (!this.geometries.has(VILLAGE)) this.geometries.set(VILLAGE, geometryOf(manifest, village));
    this.murals ??= new IsoMurals(muralWalls, manifest, assets.characterLights, {
      load: (url) => assets.loadBitmap(url),
      sample: (set, image, crop, read) => this.sampleScenery(set, image, crop, read),
      paint: (key, bitmap, box, transform) => {
        this.textures.addCanvas(key, skewed(bitmap, box, transform));
      },
      unpaint: (key) => this.textures.remove(key),
      image: (key, x, y) => this.add.image(x, y, key).setOrigin(0),
    });
  }

  private async loadScenery(
    manifest: SceneryManifest,
    set: SceneSet,
    textures: string,
    url: (image: string) => string | undefined,
  ): Promise<Scenery> {
    const assets = this.assets!;
    this.charactersLoad ??= this.loadCharacters(manifest, assets);
    const images = sceneryImages(manifest);
    const [pixels, bitmaps, characters] = await Promise.all([
      assets.imagePixels(url(manifest.light_map.image)!),
      Promise.all(images.map((image) => assets.loadBitmap(url(image)!))),
      this.charactersLoad,
    ]);
    const scenery: Scenery = {
      manifest,
      lightMap: new LightMap(manifest.light_map, pixels),
      bitmaps,
      textures,
      placed: [],
      objects: new Map(),
      rank: -1,
    };
    await this.uploads.add([
      ...images.map((image, i) => () => {
        this.textures.addImage(textures + image, bitmaps[i] as unknown as HTMLImageElement);
      }),
      ...this.placing(scenery),
      () => characters.prepare(set),
    ]);
    return scenery;
  }

  private async loadCharacters(manifest: SceneryManifest, assets: Assets): Promise<IsoCharacters> {
    const { tile } = manifest;
    const inside = insideLight(INSIDE_SUN, assets.figureMetres / tile.metres, tile);
    const lights = { ...assets.characterLights, [INSIDE]: inside };
    this.characters = await IsoCharacters.load(this, tile, pixelArt(), lights);
    this.residentLights = lights;
    return this.characters;
  }

  /** From the set's loaded image if it has one, else fetched for this and closed. */
  private async sampleScenery<T>(
    set: LightingSet,
    image: string,
    crop: Box,
    read: (pixels: Pixels) => T,
  ): Promise<T> {
    const held = this.loaded.get(set);
    const index = held ? sceneryImages(held.manifest).indexOf(image) : -1;
    const url = this.assets!.imageUrl(image);
    if (index < 0 && !url) throw new Error(`No image ${image}`);
    const bitmap = index >= 0 ? held!.bitmaps[index] : await this.assets!.loadBitmap(url!);
    const sampled = new Promise<T>((resolve, reject) => {
      void this.uploads.add([
        () => {
          try {
            resolve(read(cropPixels(bitmap, crop)));
          } catch (error) {
            reject(error);
          }
        },
      ]);
    });
    try {
      return await sampled;
    } finally {
      if (index < 0) bitmap.close();
    }
  }

  private placing(scenery: Scenery): (() => void)[] {
    const { manifest, textures } = scenery;
    const place = (x: number, y: number, image: string, depth: number) => {
      const placed = {
        image: this.add.image(x, y, textures + image).setOrigin(0).setDepth(depth).setVisible(false),
        depth,
      };
      scenery.placed.push(placed);
      return placed;
    };
    return [
      ...manifest.ground.chunks.map(({ image, x, y }) => () => {
        place(x, y, image, GROUND_DEPTH);
      }),
      ...manifest.objects.map((object) => () => {
        const slices = sliceDraws(object, manifest.tile).map(({ x, y, cropX, cropWidth, depth }) => {
          const slice = place(x, y, object.image, depth);
          slice.image.setCrop(cropX, 0, cropWidth, object.height);
          return slice;
        });
        scenery.objects.set(object.id, slices);
      }),
    ];
  }

  private unloadSet(set: LightingSet): void {
    const scenery = this.loaded.get(set);
    if (!scenery) return;
    this.loaded.delete(set);
    for (const { image } of scenery.placed) image.destroy();
    for (const image of sceneryImages(scenery.manifest)) this.textures.remove(scenery.textures + image);
    for (const bitmap of scenery.bitmaps) bitmap.close();
  }

  private *sceneries(): Iterable<Scenery> {
    yield* this.loaded.values();
    for (const interior of this.interiors.values()) if (typeof interior === 'object') yield interior;
  }

  private drawLayers(drawn: readonly Drawn[], geometry: Geometry): void {
    const open = layerAlphas(drawn);
    for (const scenery of this.sceneries()) {
      const rank = drawn.findIndex((layer) => layer.scenery === scenery);
      if (rank !== scenery.rank) {
        scenery.rank = rank;
        for (const { image, depth } of scenery.placed) {
          image.setVisible(rank >= 0).setDepth(depth + Math.max(rank, 0) * PAIR_DEPTH);
        }
      }
      if (rank < 0) continue;
      for (const { image } of scenery.placed) image.setAlpha(open[rank]);
      for (const { object, cutaway } of geometry.buildings) {
        if (cutaway.alpha === 1) continue;
        const faded = layerAlphas(drawn, cutaway.alpha)[rank];
        for (const { image } of scenery.objects.get(object.id) ?? []) image.setAlpha(faded);
      }
    }
  }

  /** Hidden off the village. */
  private drawMurals(dt: number, layers: readonly Layer[], village: Geometry | undefined): void {
    const lit = layers.map(({ set, weight }) => ({
      weight,
      light: this.assets!.characterLights[set],
      lightMap: this.loaded.get(set)!.lightMap,
    }));
    this.murals?.draw(
      dt,
      layers,
      (feet) => residentLight(lit, feet).tint,
      (id) => (village ? (village.buildings.find(({ object }) => object.id === id)?.cutaway.alpha ?? 1) : 0),
    );
  }

  private figureAt(position: Position, { manifest, heightAt }: Geometry): Figure {
    return figureAt(position, manifest.tile, heightAt, this.characters!.frame);
  }

  private spriteOf(id: string): ScreenSprite | undefined {
    const position = world.positionOf(id);
    const geometry = this.geometries.get(world.map);
    const characters = this.characters;
    if (!geometry || !characters || !position) return undefined;
    const figure = this.figureAt(position, geometry);
    const box = figureBox(figure, this.cameras.main, characters.frame);
    return { box, depth: figure.depth, opaqueAt: (point) => characters.opaqueAt(id, box, point) };
  }

  private cutAway(player: Figure, dt: number, { manifest, buildings }: Geometry): void {
    for (const { object, cutaway } of buildings) {
      cutaway.update(hides(object, player, manifest.tile), dt);
    }
  }

  private follow(player: Figure, { manifest }: Geometry): void {
    const camera = this.cameras.main;
    const zoom = isoZoom(camera.width, window.devicePixelRatio, manifest.tile);
    if (zoom !== camera.zoom) camera.setZoom(zoom);
    const target = { x: player.x, y: (player.top + player.bottom) / 2 };
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

async function fetchManifest(url: string): Promise<SceneryManifest> {
  return (await (await fetch(url)).json()) as SceneryManifest;
}
