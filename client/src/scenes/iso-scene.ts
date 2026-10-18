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
  mapOf,
  maps,
  MAX_FRAME_SECONDS,
  MoveThrottle,
  tileOf,
  village,
  VILLAGE,
  world,
  type Body,
  type Direction,
  type Point,
  type TiledMap,
} from '../world';
import {
  CLOCK_WAIT_MS,
  Cutaway,
  cutawaysOf,
  DECODES_AT_ONCE,
  DEFAULT_HOUR,
  figureAt,
  figureBox,
  framesOn,
  gridDirection,
  GROUND_DEPTH,
  groundHeights,
  hides,
  INSIDE,
  INSIDE_SUN,
  insideLight,
  InteriorLoader,
  interiorsWanted,
  isoScroll,
  isoZoom,
  layerAlphas,
  Limit,
  LightMap,
  PAIR_DEPTH,
  residentLight,
  sceneryImages,
  screenAligned,
  seatAt,
  seatsOf,
  SetLoader,
  simClock,
  sliceDraws,
  Talkers,
  UPLOAD_MS_PER_FRAME,
  uploadImages,
  Uploads,
  type Figure,
  type Layer,
  type LightingSet,
  type Rgb,
  type SceneryManifest,
  type SceneryObject,
  type SceneSet,
  type Seat,
  type SetLight,
  type TextureStage,
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
import { galleryFrames, IsoPaintings, isFrame, type PaintingStage } from '../world/iso/paintings';
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
  textures: string;
  placed: Placed[];
  objects: Map<string, Placed[]>;
  rank: number;
};
type Drawn = { scenery: Scenery; set: SceneSet; weight: number };
type Geometry = {
  manifest: SceneryManifest;
  heightAt: (position: Position) => number;
  /** `ids` are the object's and those of the frames on it, which fade with it. */
  buildings: { object: SceneryObject; ids: string[]; cutaway: Cutaway }[];
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
    buildings: cutawaysOf(manifest.objects).map((object) => ({
      object,
      ids: [object, ...framesOn(object, manifest.objects)].map(({ id }) => id),
      cutaway: new Cutaway(),
    })),
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
  private readonly interiors = new InteriorLoader(
    (map) => this.loadInterior(map),
    (map, scenery) => this.unloadInterior(map, scenery),
  );
  private readonly geometries = new Map<string, Geometry>();
  private readonly uploads = new Uploads();
  private readonly decodes = new Limit(DECODES_AT_ONCE);
  private keys!: Keys;
  private fade!: Phaser.GameObjects.Rectangle;
  private assets?: Assets;
  private residentLights?: Record<SceneSet, SetLight>;
  private charactersLoad?: Promise<IsoCharacters>;
  private characters?: IsoCharacters;
  private murals?: IsoMurals<ImageBitmap>;
  private readonly paintings = new Map<string, IsoPaintings<ImageBitmap>>();
  private readonly seats = new Map<string, Map<string, Seat>>();
  private readonly talkers = new Talkers();
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
      server.on('line', ({ line }) => this.talkers.heard(line.speaker, line.duration)),
      setMuralView({
        wallAt: ({ x, y }) =>
          world.map === VILLAGE ? this.murals?.wallAt(this.cameras.main.getWorldPoint(x, y)) : undefined,
      }),
      () => this.murals?.destroy(),
      () => this.paintings.forEach((paintings) => paintings.destroy()),
      () => interactables.update(undefined),
      this.onContextRestored(() => {
        this.sets.reset();
        this.interiors.reset();
      }),
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
    this.interiors.update(this.interiorsWanted(player.position), time / 1000);
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
    if (drawn.length === 0 || !characters || !residentLights || !geometry || !collision) return;
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

    const bodies = new Map<string, Body>(
      [...world.here()].map(({ id, mover, pose, facing }) => [
        id,
        { position: mover.position, walking: mover.walking, pose, facing },
      ]),
    );
    bodies.set(PLAYER_ID, player);
    const lit = drawn.map(({ scenery, set, weight }) => ({
      weight,
      light: residentLights[set],
      lightMap: scenery.lightMap,
    }));
    const at = (position: Position) => this.figureAt(position, geometry);
    characters.draw(bodies, dt, at, drawn, (feet) => residentLight(lit, feet), {
      seatAt: (position) => this.seatAt(map, position),
      talking: (id) => this.talkers.talking(id),
    });
    this.drawMurals(dt, villageLayers, map === VILLAGE ? geometry : undefined);
    this.drawPaintings(dt, map, (feet) => residentLight(lit, feet).tint, geometry);
    this.follow(figure, geometry);
  }

  private async start(): Promise<void> {
    await simClock.known(CLOCK_WAIT_MS);
    this.assets = await import('../world/iso/assets');
  }

  /** Restored textures whose bitmaps are closed are empty, so `reload` loads the scenery again. */
  private onContextRestored(reload: () => void): () => void {
    const { renderer } = this.game;
    renderer.on(Phaser.Renderer.Events.RESTORE_WEBGL, reload);
    return () => renderer.off(Phaser.Renderer.Events.RESTORE_WEBGL, reload);
  }

  /** Whether the map can be drawn, starting its scenery loading if it hasn't. */
  private ready(map: string): boolean {
    if (map === VILLAGE) return this.geometries.has(VILLAGE) && this.sets.layers.length > 0;
    return this.interior(map) !== undefined;
  }

  private interior(map: string): Scenery | undefined {
    return this.assets?.interiorManifestUrl(map) ? this.interiors.get(map) : undefined;
  }

  private interiorsWanted(position: Position): string[] {
    return interiorsWanted(position, doorsOn(mapOf(position))).filter((map) =>
      this.assets?.interiorManifestUrl(map),
    );
  }

  private drawnOn(map: string, villageLayers: readonly Layer[]): Drawn[] {
    if (map === VILLAGE) {
      return villageLayers.map(({ set, weight }) => ({ scenery: this.loaded.get(set)!, set, weight }));
    }
    const interior = this.interior(map);
    return interior ? [{ scenery: interior, set: INSIDE, weight: 1 }] : [];
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
  }

  private async loadInterior(map: string): Promise<Scenery> {
    const assets = this.assets!;
    const [manifest, tiled] = await Promise.all([fetchManifest(assets.interiorManifestUrl(map)!), loadMap(map)]);
    const scenery = await this.loadScenery(manifest, INSIDE, 'iso/interiors/', assets.interiorImageUrl);
    this.geometries.set(map, geometryOf(manifest, tiled));
    if (manifest.objects.some(isFrame)) {
      this.paintings.set(map, new IsoPaintings(galleryFrames, manifest, this.paintingStage()));
    }
    return scenery;
  }

  private unloadInterior(map: string, scenery: Scenery): void {
    this.unloadScenery(scenery);
    this.paintings.get(map)?.destroy();
    this.paintings.delete(map);
    this.geometries.delete(map);
  }

  private paintingStage(): PaintingStage<ImageBitmap> {
    return {
      load: (url) => this.decode(url),
      paint: (key, bitmap, box, transform) => {
        this.textures.addCanvas(key, skewed(bitmap, box, transform));
      },
      unpaint: (key) => this.textures.remove(key),
      image: (key, x, y) => this.add.image(x, y, key).setOrigin(0),
    };
  }

  private async loadSet(set: LightingSet): Promise<void> {
    const assets = this.assets!;
    const manifest = await fetchManifest(assets.manifestUrl(set)!);
    const scenery = await this.loadScenery(manifest, set, 'iso/', assets.imageUrl);
    this.loaded.set(set, scenery);
    if (!this.geometries.has(VILLAGE)) this.geometries.set(VILLAGE, geometryOf(manifest, village));
    this.murals ??= new IsoMurals(muralWalls, manifest, assets.characterLights, {
      load: (url) => this.decode(url),
      sample: (_set, image, crop, read) => this.sampleScenery(image, crop, read),
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
    const [pixels, characters] = await Promise.all([
      assets.imagePixels(url(manifest.light_map.image)!),
      this.charactersLoad,
    ]);
    const images = sceneryImages(manifest).map((image) => ({ key: textures + image, url: url(image)! }));
    await uploadImages(images, this.textureStage(), this.uploads, this.decodes);
    const scenery: Scenery = {
      manifest,
      lightMap: new LightMap(manifest.light_map, pixels),
      textures,
      placed: [],
      objects: new Map(),
      rank: -1,
    };
    await this.uploads.add([...this.placing(scenery), () => characters.prepare(set)]);
    return scenery;
  }

  private textureStage(): TextureStage<ImageBitmap> {
    return {
      decode: (url) => this.assets!.loadBitmap(url),
      add: (key, bitmap) => {
        this.textures.addImage(key, bitmap as unknown as HTMLImageElement);
      },
      remove: (key) => this.textures.remove(key),
      keepsBitmaps: this.renderer.type === Phaser.CANVAS,
    };
  }

  private decode(url: string): Promise<ImageBitmap> {
    return this.decodes.run(() => this.assets!.loadBitmap(url));
  }

  private async loadCharacters(manifest: SceneryManifest, assets: Assets): Promise<IsoCharacters> {
    const { tile } = manifest;
    const inside = insideLight(INSIDE_SUN, assets.figureMetres / tile.metres, tile);
    const lights = { ...assets.characterLights, [INSIDE]: inside };
    this.characters = await IsoCharacters.load(this, tile, pixelArt(), lights);
    this.residentLights = lights;
    return this.characters;
  }

  /** Fetched for this, read within the upload budget and closed. */
  private async sampleScenery<T>(image: string, crop: Box, read: (pixels: Pixels) => T): Promise<T> {
    const url = this.assets!.imageUrl(image);
    if (!url) throw new Error(`No image ${image}`);
    return this.decodes.run(async () => {
      const bitmap = await this.assets!.loadBitmap(url);
      try {
        return await new Promise<T>((resolve, reject) => {
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
      } finally {
        bitmap.close();
      }
    });
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
    this.unloadScenery(scenery);
  }

  private unloadScenery({ placed, manifest, textures }: Scenery): void {
    for (const { image } of placed) image.destroy();
    for (const image of sceneryImages(manifest)) this.textures.remove(textures + image);
  }

  private *sceneries(): Iterable<Scenery> {
    yield* this.loaded.values();
    yield* this.interiors.loaded();
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
      for (const { ids, cutaway } of geometry.buildings) {
        if (cutaway.alpha === 1) continue;
        const faded = layerAlphas(drawn, cutaway.alpha)[rank];
        for (const id of ids) for (const { image } of scenery.objects.get(id) ?? []) image.setAlpha(faded);
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

  /** Only the player's map's, each fading with the wall it hangs on. */
  private drawPaintings(dt: number, map: string, light: (feet: Point) => Rgb, { buildings }: Geometry): void {
    const alphaOf = (frame: string) => buildings.find(({ ids }) => ids.includes(frame))?.cutaway.alpha ?? 1;
    for (const [on, paintings] of this.paintings) paintings.draw(dt, on === map, light, alphaOf);
  }

  private seatAt(map: string, position: Position): Seat | undefined {
    const tiled = maps[map];
    if (!tiled) return undefined;
    let seats = this.seats.get(map);
    if (!seats) this.seats.set(map, (seats = seatsOf(tiled)));
    return seatAt(seats, tileOf(position));
  }

  private figureAt(position: Position, { manifest, heightAt }: Geometry): Figure {
    return figureAt(position, manifest.tile, heightAt, this.characters!.frame);
  }

  private spriteOf(id: string): ScreenSprite | undefined {
    const position = world.positionOf(id);
    const geometry = this.geometries.get(world.map);
    const characters = this.characters;
    if (!geometry || !characters || !position) return undefined;
    const figure = characters.figureOf(id) ?? this.figureAt(position, geometry);
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
