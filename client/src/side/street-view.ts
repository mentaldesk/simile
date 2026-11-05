import Phaser from 'phaser';
import type { Frame, Wall } from '../net';
import { LAYER_PLACES, landmarkX, layerCopies, parallaxY, streetCentreY, type Copies, type Point } from './camera';
import { DEPTH } from './depths';
import { dropShadow, furnitureKey, placeDerived, placeFurniture, placeParts, tileAlong, Tints, type TintGroup } from './draw';
import { House } from './house';
import {
  coverCrop,
  feetOf,
  FURNITURE_DROP_M,
  frontPlacement,
  furniturePlacement,
  groundRuns,
  groundTop,
  ledges,
  muralRect,
  PPM,
  roofHeight,
  streetRow,
  stretchWidth,
  TILE,
  TILE_M,
  xOf,
  type Rect,
} from './layout';
import { colour, hazeOf, layerTint, overflow, type Light } from './light';
import type { Placed, SideMap, Village } from './maps';
import { climbRuns } from './runs';
import type { LayerName, Rgb, SceneryManifest } from './scenery';
import type { SideTextures } from './textures';

const LIFT_M = 1.2;
const OPEN_SECONDS = 0.45;
/** For views wider than a short street. */
const GROUND_BEYOND_M = 40;
const GROUND_DEPTH_M = 40;
const FOREGROUND_SCALE = 1.4;
const FOREGROUND_BLUR = 6;
/** The street lamp's, for a manifest that doesn't say. */
export const LAMP_HEAD_M = 3.31;
/** A city layer without one in the manifest's parallax. */
export const CITY_PARALLAX = 0.1;
const LAMP_LIGHT_M = 3.6;
const BLOOM = 0.8;
const LADDER_ABOVE_M = 0.6;
/** World px a px of a signpost's texture. */
const SIGN_SCALE = 0.6;

type Image = Phaser.GameObjects.Image;
/** By street id, the platforms it draws in place of the village's. */
type Below = SceneryManifest & { platforms_below?: Record<string, Record<string, string>> };

type Layer = {
  name: LayerName;
  texture: string;
  frame: { frame: string; width: number; height: number };
  parallax: number;
  scale: number;
  baseY: number;
  /** The city's tint is its own. */
  group?: TintGroup;
  depth: number;
  hazeDepth: number;
  images: Image[];
  /** Haze over the far and mid layers, or the sky's additive top-up. */
  extra: Image[];
  extraOn: boolean;
};

type Landmark = { x: number; image: Image; haze: Image; glows: Image[] };

type Front = {
  building: Placed;
  baseY: number;
  front: Image;
  shadow: Image;
  glow: Image;
  bloom: Image;
  roof?: Image;
  house?: House;
  murals: Map<string, { image: Image; y: number; rect: Rect }>;
  open: number;
};

export type Content = {
  village: Village;
  scenery: SceneryManifest;
  pieceUrl(key: string): string;
};

export class StreetView {
  readonly map: SideMap;
  readonly feet: number;
  /** The foreground's reference. */
  readonly lowest: number;
  readonly width: number;
  readonly tints = new Tints();
  private readonly scene: Phaser.Scene;
  private readonly textures: SideTextures;
  private readonly manifest: SceneryManifest;
  private readonly layers: Layer[] = [];
  private readonly fronts: Front[] = [];
  private readonly byName = new Map<string, Front>();
  private readonly rides = new Map<House, number>();
  private readonly lamps: Image[] = [];
  private readonly landmarks: Landmark[] = [];
  private readonly cityBaseY: number;
  private readonly cityParallax: number;
  private readonly rgb: Rgb = [1, 1, 1];
  private cityTint = 0xffffff;
  private readonly props: { x: number; images: Image[] }[] = [];
  private readonly owned: Phaser.GameObjects.GameObject[] = [];
  private readonly copies: Copies = { first: 0, count: 0, y: 0 };
  private readonly view = { left: 0, width: 0, centre: { x: 0, y: 0 } as Point };
  private glow = 0;
  private murals = '';

  constructor(scene: Phaser.Scene, textures: SideTextures, content: Content, map: SideMap) {
    this.scene = scene;
    this.textures = textures;
    this.manifest = content.scenery;
    this.map = map;
    this.feet = streetRow(map) * TILE;
    this.lowest = Math.max(...groundRuns(map, content.scenery).map(({ row }) => row)) * TILE;
    this.width = map.width * TILE;
    this.cityBaseY = this.feet + LAYER_PLACES.city.bottom * PPM;
    this.cityParallax = content.scenery.parallax.city ?? CITY_PARALLAX;
    this.buildLayers();
    this.buildLandmarks();
    this.buildGround();
    this.buildClimbs();
    for (const building of map.buildings) this.buildFront(building, content.village);
    for (const item of map.furniture) this.buildFurniture(item);
    this.buildSignposts(content.village);
  }

  static pieces(content: Content, map: SideMap): string[] {
    const { scenery: manifest, village } = content;
    const layers = StreetView.layersOf(manifest, map);
    const buildings = map.buildings.flatMap(({ name }) => {
      const entry = manifest.buildings[name];
      const floors = entry && village.floors(name).length > 0 ? House.pieces(manifest, name, village) : [];
      return entry ? [entry.front, entry.glow, ...floors] : [];
    });
    const furniture = map.furniture.map((item) => furnitureKey(manifest, item, map.id));
    const grounds = groundRuns(map, manifest).map(({ key }) => key);
    const platforms = StreetView.platformsOf(manifest, map);
    const climbs = [platforms.steps, platforms.ladder, platforms.ledge];
    const landmarks = StreetView.landmarksOf(manifest, map).flatMap(({ piece, glow }) => [piece, glow]);
    const all = [...Object.values(layers), ...buildings, ...furniture, ...grounds, ...climbs, ...landmarks];
    return [...new Set(all)].filter((key): key is string => !!key && !!manifest.pieces[key]?.file);
  }

  /** Its layers, with no city under the village. */
  static layersOf(manifest: SceneryManifest, map: SideMap): Partial<SceneryManifest['streets'][string]> {
    const layers = manifest.streets[map.id] ?? {};
    return map.underground ? { ...layers, city: undefined } : layers;
  }

  /** Its own ladder, steps and ledge under the village, and the village's where it has none. */
  static platformsOf(manifest: SceneryManifest, map: SideMap): Record<string, string> {
    return { ...manifest.platforms, ...(manifest as Below).platforms_below?.[map.id] };
  }

  /** The landmarks standing along it, each with where. */
  static landmarksOf(manifest: SceneryManifest, map: SideMap) {
    if (map.underground) return [];
    return Object.values(manifest.landmarks ?? {}).flatMap(({ piece, glow, at }) =>
      at[map.id] === undefined || !manifest.pieces[piece] ? [] : [{ piece, glow, at: at[map.id] }],
    );
  }

  house(name: string): House | undefined {
    return this.byName.get(name)?.house;
  }

  /** Its front is off, coming off or going back on. */
  isOpen(name: string | undefined): boolean {
    return !!name && (this.byName.get(name)?.open ?? 0) > 0;
  }

  /** How far on the front over `x` is: below 1, what's in front of it is left out. */
  ghost(x: number): number {
    let on = 1;
    for (const { building, open } of this.fronts) {
      if (open > 0 && x >= building.x * TILE && x <= (building.x + building.w) * TILE) on = Math.min(on, 1 - open);
    }
    return on;
  }

  ride(building: string, x: number, feet: number, from: number, to: number): void {
    const house = this.house(building);
    if (!house) return;
    const count = this.rides.get(house) ?? 0;
    house.ride(count, x, feet, from, to);
    this.rides.set(house, count + 1);
  }

  endRides(): void {
    for (const { house } of this.fronts) {
      if (!house) continue;
      house.endRides(this.rides.get(house) ?? 0);
      this.rides.set(house, 0);
    }
  }

  update(worldView: Phaser.Geom.Rectangle, light: Light, lightChanged: boolean, open: string | undefined, dt: number): void {
    if (lightChanged) this.light(light);
    this.view.left = worldView.x;
    this.view.width = worldView.width;
    this.view.centre.x = worldView.centerX;
    this.view.centre.y = worldView.centerY;
    const streetY = streetCentreY(this.feet, worldView);
    for (const layer of this.layers) this.place(layer, worldView, streetY);
    this.placeLandmarks(streetY);
    const step = dt / OPEN_SECONDS;
    let moved = false;
    for (const front of this.fronts) {
      const target = front.building.name === open ? 1 : 0;
      const before = front.open;
      front.open = target > before ? Math.min(target, before + step) : Math.max(target, before - step);
      if (front.open !== before || lightChanged) this.openFront(front);
      moved ||= front.open !== before;
    }
    if (moved) {
      for (const { x, images } of this.props) {
        const shown = this.ghost(x) === 1;
        for (const image of images) image.setVisible(shown);
      }
    }
  }

  setMurals(walls: readonly Wall[], load: (url: string) => Promise<string>): void {
    const mine = walls.filter((wall) => wall.map === this.map.id && wall.mural);
    const signature = mine.map((wall) => `${wall.id}:${wall.mural!.image}`).join('|');
    if (signature === this.murals) return;
    this.murals = signature;
    for (const front of this.fronts) {
      for (const { image } of front.murals.values()) image.destroy();
      front.murals.clear();
    }
    for (const wall of mine) {
      const front = this.fronts.find(({ building: b }) => b.x <= wall.x && wall.x < b.x + b.w);
      if (!front) continue;
      const eaves = this.manifest.pieces[this.manifest.buildings[front.building.name].front].eaves;
      const rect = muralRect(wall, eaves);
      void load(wall.mural!.image).then((texture) => {
        if (!this.scene.sys.isActive() || this.murals !== signature) return;
        const { width, height } = this.scene.textures.getFrame(texture);
        const crop = coverCrop(width, height, rect);
        const [x, y] = [rect.x - crop.x * crop.scale, rect.y - crop.y * crop.scale];
        const image = this.scene.add.image(x, y, texture).setOrigin(0, 0).setDepth(DEPTH.mural);
        image.setScale(crop.scale).setCrop(crop.x, crop.y, crop.width, crop.height);
        front.murals.set(wall.id, { image: this.tints.add('ground', image), y, rect });
        this.owned.push(image);
        this.openFront(front);
      });
    }
  }

  /** The mural wall drawn at a world point, while its front is on. */
  muralAt(x: number, y: number): string | undefined {
    for (const { murals, open } of this.fronts) {
      if (open > 0) continue;
      for (const [id, { rect }] of murals) {
        if (x >= rect.x && x < rect.x + rect.width && y >= rect.y && y < rect.y + rect.height) return id;
      }
    }
    return undefined;
  }

  setPaintings(frames: readonly Frame[], load: (url: string) => Promise<string>): void {
    for (const { house } of this.fronts) house?.hang(frames, load);
  }

  destroy(): void {
    for (const object of this.owned) object.destroy();
    for (const front of this.fronts) {
      front.house?.destroy();
      for (const { image } of front.murals.values()) image.destroy();
    }
  }

  private own<T extends Phaser.GameObjects.GameObject>(object: T): T {
    this.owned.push(object);
    return object;
  }

  private light(light: Light): void {
    this.tints.apply(light);
    this.glow = light.glow;
    this.cityTint = colour(layerTint(light, 'city', this.rgb));
    const cityHaze = colour(light.haze);
    const cityHazeAmount = hazeOf(light, 'city');
    for (const { image, haze, glows } of this.landmarks) {
      image.setTint(this.cityTint);
      haze.setTintFill(cityHaze).setAlpha(cityHazeAmount);
      glows.forEach((glow, i) => glow.setAlpha(light.glow * (i === 0 ? 1 : BLOOM)).setVisible(light.glow > 0));
    }
    for (const layer of this.layers) {
      if (!layer.group) for (const image of layer.images) image.setTint(this.cityTint);
      if (layer.name === 'sky') {
        const extra = overflow(light.sky);
        layer.extraOn = extra > 0;
        for (const image of layer.extra) image.setTint(extra);
      } else {
        const amount = hazeOf(light, layer.name);
        const haze = colour(light.haze);
        for (const image of layer.extra) image.setTintFill(haze).setAlpha(amount);
      }
    }
    for (const lamp of this.lamps) lamp.setAlpha(light.glow).setVisible(light.glow > 0);
  }

  private place(layer: Layer, view: Phaser.Geom.Rectangle, streetY: number): void {
    const sky = layer.name === 'sky';
    const scale = sky ? view.height / layer.frame.height : layer.scale;
    const width = layer.frame.width * scale;
    layerCopies(layer.parallax, width, this.view, layer.baseY, streetY, this.copies);
    const { first, count } = this.copies;
    const y = sky ? view.bottom : this.copies.y;
    while (layer.images.length < count) this.copy(layer);
    const { extraOn } = layer;
    for (let i = 0; i < layer.images.length; i++) {
      const shown = i < count;
      const x = first + i * width;
      layer.images[i].setPosition(x, y).setScale(scale).setVisible(shown);
      layer.extra[i].setPosition(x, y).setScale(scale).setVisible(shown && extraOn);
    }
  }

  private copy(layer: Layer): void {
    const { texture, frame, depth, hazeDepth } = layer;
    const image = this.own(this.scene.add.image(0, 0, texture, frame.frame).setOrigin(0, 1).setDepth(depth));
    layer.images.push(layer.group ? this.tints.add(layer.group, image) : image.setTint(this.cityTint));
    const extra = this.own(this.scene.add.image(0, 0, texture, frame.frame).setOrigin(0, 1).setDepth(hazeDepth));
    if (layer.name === 'sky') extra.setBlendMode(Phaser.BlendModes.ADD).setTint(0);
    else extra.setTintFill(0).setAlpha(0);
    layer.extra.push(extra);
  }

  private buildLayers(): void {
    const { manifest, map } = this;
    const keys = StreetView.layersOf(manifest, map);
    const depths: Partial<Record<LayerName, number>> = {
      sky: DEPTH.sky,
      city: DEPTH.city,
      far: DEPTH.far,
      mid: DEPTH.mid,
      near: DEPTH.near,
      foreground: DEPTH.foreground,
    };
    for (const name of ['sky', 'city', 'far', 'mid', 'near', 'foreground'] as const) {
      const key = keys[name];
      const piece = key ? manifest.pieces[key] : undefined;
      if (!key || !piece) continue;
      const place = name === 'sky' ? { bottom: 0 } : LAYER_PLACES[name];
      const metres = name === 'foreground' ? piece.height * FOREGROUND_SCALE : (place.height ?? piece.height);
      const source = name === 'foreground' ? this.textures.blurred(key, FOREGROUND_BLUR).name : key;
      const tile = this.textures.tileFrame(source);
      this.layers.push({
        name,
        texture: this.textures.key(source),
        frame: { frame: tile.frame, width: tile.width, height: piece.size[1] },
        parallax: name === 'city' ? this.cityParallax : manifest.parallax[name],
        scale: (metres * PPM) / piece.size[1],
        baseY: (name === 'foreground' ? this.lowest : this.feet) + place.bottom * PPM,
        group: name === 'city' ? undefined : name,
        depth: depths[name]!,
        hazeDepth: name === 'city' ? DEPTH.cityHaze : depths[name]! + 1,
        images: [],
        extra: [],
        extraOn: name === 'city' || name === 'far' || name === 'mid',
      });
    }
  }

  /** Once along the street, at the city's parallax, standing on the city's bottom edge. */
  private buildLandmarks(): void {
    const { manifest, map, scene, textures } = this;
    for (const { piece: key, glow, at } of StreetView.landmarksOf(manifest, map)) {
      const piece = manifest.pieces[key];
      const anchor = piece.anchor ?? [0.5, 1];
      const scale = (piece.height * PPM) / piece.size[1];
      const source = { width: piece.size[0], height: piece.size[1] };
      const image = this.own(scene.add.image(0, 0, textures.key(key)).setOrigin(...anchor).setScale(scale));
      const haze = this.own(scene.add.image(0, 0, textures.key(key)).setOrigin(...anchor).setScale(scale));
      image.setDepth(DEPTH.landmark).setTint(this.cityTint);
      haze.setDepth(DEPTH.landmarkHaze).setTintFill(0).setAlpha(0);
      const glows = manifest.pieces[glow]
        ? [textures.light(glow, 0.5), textures.light(glow, 0.25, 8)].map((derived) =>
            this.own(placeDerived(scene, derived, source, anchor, 0, 0, scale))
              .setBlendMode(Phaser.BlendModes.ADD)
              .setDepth(DEPTH.landmarkGlow)
              .setVisible(false),
          )
        : [];
      this.landmarks.push({ x: at * this.width, image, haze, glows });
    }
  }

  private placeLandmarks(streetY: number): void {
    const { centre } = this.view;
    const y = parallaxY(this.cityParallax, this.cityBaseY, centre.y, streetY);
    for (const { x, image, haze, glows } of this.landmarks) {
      const at = landmarkX(x, this.cityParallax, centre.x);
      image.setPosition(at, y);
      haze.setPosition(at, y);
      for (const glow of glows) glow.setPosition(at, y);
    }
  }

  private buildGround(): void {
    const { manifest, map, scene, textures } = this;
    const runs = groundRuns(map, manifest);
    if (runs.length > 0) {
      runs[0].x0 -= GROUND_BEYOND_M / TILE_M;
      runs.at(-1)!.x1 += GROUND_BEYOND_M / TILE_M;
    }
    for (const run of runs) {
      const piece = manifest.pieces[run.key];
      if (!piece) continue;
      const scale = (piece.height * PPM) / piece.size[1];
      const top = groundTop(run.row * TILE, piece);
      const [x0, x1] = [run.x0 * TILE, run.x1 * TILE];
      const tile = textures.tileFrame(run.key);
      for (const image of tileAlong(scene, textures.key(run.key), tile, x0, x1, top, scale)) {
        this.tints.add('ground', this.own(image.setDepth(DEPTH.ground)));
      }
      const below = top + (piece.size[1] * scale) / 2;
      const fill = this.own(scene.add.rectangle(x0, below, x1 - x0, GROUND_DEPTH_M * PPM).setOrigin(0, 0));
      this.tints.fill('ground', fill.setDepth(DEPTH.groundFill), textures.bottomColour(run.key));
    }
    const { ledge } = StreetView.platformsOf(manifest, map);
    for (const { x0, x1, row } of ledges(map)) {
      const derived = textures.stretched(ledge, Math.round((x1 - x0) * TILE));
      for (const image of placeParts(scene, derived, textures.size(derived.name), [0, 0], x0 * TILE, row * TILE)) {
        this.tints.add('ground', this.own(image.setDepth(DEPTH.ledge)));
      }
    }
  }

  private buildClimbs(): void {
    const { manifest, map, scene, textures } = this;
    const platforms = StreetView.platformsOf(manifest, map);
    for (const { kind, path } of climbRuns(map)) {
      const [foot, head] = [path.points[0], path.points.at(-1)!];
      if (kind === 'stairs') {
        const key = platforms.steps;
        const image = scene.add.image(xOf((foot.x + head.x) / 2), feetOf(foot.y), textures.key(key));
        image.setOrigin(0.5, 1).setDisplaySize(Math.abs(head.x - foot.x) * TILE, (foot.y - head.y) * TILE);
        this.tints.add('ground', this.own(image.setFlipX(head.x < foot.x).setDepth(DEPTH.steps)));
      } else {
        const rungs = path.points.filter((point) => point.x === foot.x);
        const top = rungs[rungs.length - 1];
        const key = platforms.ladder;
        const piece = manifest.pieces[key];
        const height = (foot.y - top.y) * TILE + LADDER_ABOVE_M * PPM;
        const image = scene.add.image(xOf(foot.x), feetOf(foot.y), textures.key(key)).setOrigin(0.5, 1);
        this.tints.add('ground', this.own(image.setScale(1, height / piece.size[1]).setDepth(DEPTH.steps)));
      }
    }
  }

  private buildFront(building: Placed, village: Village): void {
    const { manifest, scene, textures } = this;
    const entry = manifest.buildings[building.name];
    const piece = entry && manifest.pieces[entry.front];
    if (!piece) return;
    const place = frontPlacement(building, piece);
    const anchor = [place.originX, place.originY] as const;
    const source = { width: piece.size[0], height: piece.size[1] };
    const key = textures.key(entry.front);
    const front = scene.add.image(place.x, place.y, key).setOrigin(...anchor).setDepth(DEPTH.front);
    const shadow = dropShadow(scene, textures, entry.front, anchor, place.x, place.y, {
      ppm: PPM,
      scale: 0.25,
      blur: 5,
      alpha: 0.3,
    }).setDepth(DEPTH.frontShadow);
    const glow = placeDerived(scene, textures.light(entry.glow, 0.5), source, anchor, place.x, place.y);
    const bloom = placeDerived(scene, textures.light(entry.glow, 0.25, 8), source, anchor, place.x, place.y);
    for (const light of [glow, bloom]) light.setBlendMode(Phaser.BlendModes.ADD).setDepth(DEPTH.glow).setVisible(false);
    this.tints.add('ground', front);
    [front, shadow, glow, bloom].forEach((image) => this.own(image));
    const result: Front = { building, baseY: place.y, front, shadow, glow, bloom, murals: new Map(), open: 0 };
    if (building.props.interior && village.floors(building.name).length > 0) {
      const roof = scene.add.image(place.x, place.y, key).setOrigin(...anchor).setDepth(DEPTH.roof);
      roof.setCrop(0, 0, piece.size[0], roofHeight(piece)).setVisible(false);
      result.roof = this.tints.add('ground', this.own(roof));
      result.house = new House(scene, textures, manifest, this.tints, building, village);
    }
    this.fronts.push(result);
    this.byName.set(building.name, result);
  }

  private buildFurniture(item: Placed): void {
    const { manifest, map, scene, textures } = this;
    const key = furnitureKey(manifest, item, map.id);
    if (!key) return;
    const stretch = manifest.furniture[item.name]?.stretch ? stretchWidth(item) : undefined;
    const place = furniturePlacement(item, map);
    const anchor = [place.originX, place.originY] as const;
    const { images, shadows } = placeFurniture(scene, textures, key, stretch, anchor, place.x, place.y, PPM);
    for (const shadow of shadows) this.own(shadow.setDepth(DEPTH.streetShadow));
    for (const image of images) this.tints.add('ground', this.own(image.setDepth(DEPTH.streetFurniture)));
    this.props.push({ x: place.x, images: [...images, ...shadows] });
    const head = manifest.furniture[item.name]?.light ?? (item.name === 'lamp' ? LAMP_HEAD_M : undefined);
    if (head !== undefined) {
      const lamp = scene.add.image(place.x, place.y - head * PPM, textures.lamp());
      lamp.setScale((LAMP_LIGHT_M * PPM) / 256).setBlendMode(Phaser.BlendModes.ADD).setDepth(DEPTH.lampGlow);
      this.lamps.push(this.own(lamp.setVisible(false)));
    }
  }

  /** A fingerpost at each way to another street, naming it. */
  private buildSignposts(village: Village): void {
    const { map, scene, textures } = this;
    for (const link of map.links) {
      const there = village.map(link.to.map);
      if (link.kind !== 'door' || there?.kind !== 'street') continue;
      const key = textures.signpost(there.label ?? there.id);
      const [x, y] = [xOf(link.x), feetOf(link.y) + FURNITURE_DROP_M * PPM];
      const shadow = dropShadow(scene, textures, key, [0.5, 1], x, y, { ppm: PPM, scale: 0.25 });
      this.own(shadow.setScale(shadow.scaleX * SIGN_SCALE).setDepth(DEPTH.streetShadow));
      const image = scene.add.image(x, y, textures.key(key)).setOrigin(0.5, 1).setScale(SIGN_SCALE);
      this.tints.add('ground', this.own(image.setDepth(DEPTH.streetFurniture)));
      this.props.push({ x, images: [image, shadow] });
    }
  }

  private openFront(front: Front): void {
    const { open } = front;
    const lift = open * LIFT_M * PPM;
    const shut = 1 - open;
    front.front.setY(front.baseY - lift).setAlpha(shut);
    front.shadow.setAlpha(0.3 * shut);
    const glow = this.glow * shut;
    front.glow.setY(front.baseY - lift).setAlpha(glow).setVisible(glow > 0);
    front.bloom.setY(front.baseY - lift).setAlpha(glow * BLOOM).setVisible(glow > 0);
    for (const { image, y } of front.murals.values()) image.setAlpha(shut).setY(y - lift);
    front.roof?.setVisible(open > 0);
    front.house?.setShown(open > 0);
  }
}
