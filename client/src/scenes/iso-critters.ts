import Phaser from 'phaser';
import { village } from '../world';
import {
  DEFAULT_HOUR,
  PIXEL_SCALE,
  residentLight,
  SHADOW_DEPTH,
  simClock,
  tintColour,
  type IsoTile,
  type LitLayer,
  type SceneryManifest,
} from '../world/iso';
import { CRITTER_BOXES, critterSheet } from '../world/iso/critter-art';
import { CRITTERS, Critters, Water, type CritterTuning } from '../world/iso/critters';

const TEXTURE = 'iso-critters';
/** Flat on the water: over the ground and shadows, under everything standing. */
const RING_DEPTH = SHADOW_DEPTH + 0.5;
const DEPTH_TIE = 1e-3;
/** How far a critter moves, in tiles, or the sets' weights change, before its light is sampled again. */
const LIGHT_STEP = 0.125;
const WEIGHT_STEP = 0.01;

type Lit = { x: number; y: number; tint: number };

export class IsoCritters {
  private readonly critters: Critters;
  private readonly sprites: Phaser.GameObjects.Image[];
  private readonly sampled: Lit[];
  private readonly tile: IsoTile;
  private readonly waterMetres: number;
  private readonly feet = { x: 0, y: 0 };
  private readonly lights: LitLayer['light'][] = [];
  private readonly weights: number[] = [];
  private shown = false;

  constructor(scene: Phaser.Scene, manifest: SceneryManifest, tuning: CritterTuning = CRITTERS) {
    addTexture(scene);
    this.tile = manifest.tile;
    this.waterMetres = manifest.ground.heights.water ?? 0;
    this.critters = new Critters(Water.of(village), tuning);
    this.sprites = this.critters.all.map(({ kind, frame }) => {
      const { width, height, anchor } = CRITTER_BOXES[kind];
      return scene.add
        .image(0, 0, TEXTURE, frame)
        .setOrigin(anchor.x / width, anchor.y / height)
        .setScale(PIXEL_SCALE)
        .setVisible(false);
    });
    this.sampled = this.critters.all.map(() => ({ x: NaN, y: NaN, tint: -1 }));
  }

  /** `lit` is the village's light while it's drawn, or undefined to hide them. */
  draw(dt: number, lit: readonly LitLayer[] | undefined): void {
    if (!lit) {
      if (this.shown) for (const sprite of this.sprites) sprite.setVisible(false);
      this.shown = false;
      return;
    }
    this.shown = true;
    this.critters.update(dt, simClock.hour() ?? DEFAULT_HOUR);
    const relight = this.relit(lit);
    const { all } = this.critters;
    const { width, height, px_per_metre_up } = this.tile;
    for (let i = 0; i < all.length; i++) {
      const critter = all[i];
      const sprite = this.sprites[i];
      if (sprite.visible !== critter.visible) sprite.setVisible(critter.visible);
      if (!critter.visible) continue;
      const { x, y } = critter;
      if (sprite.frame.name !== critter.frame) sprite.setFrame(critter.frame);
      if (sprite.alpha !== critter.alpha) sprite.setAlpha(critter.alpha);
      const ground = ((x + y) * height) / 2;
      sprite.setPosition(((x - y) * width) / 2, ground - (this.waterMetres + critter.z) * px_per_metre_up);
      const depth = critter.kind === 'ripple' ? RING_DEPTH : ground + DEPTH_TIE;
      if (sprite.depth !== depth) sprite.setDepth(depth);
      const last = this.sampled[i];
      if (relight || Math.abs(x - last.x) > LIGHT_STEP || Math.abs(y - last.y) > LIGHT_STEP) {
        this.feet.x = last.x = x;
        this.feet.y = last.y = y;
        const tint = tintColour(residentLight(lit, this.feet).tint);
        if (tint !== last.tint) sprite.setTint((last.tint = tint));
      }
    }
  }

  private relit(lit: readonly LitLayer[]): boolean {
    let changed = lit.length !== this.lights.length;
    for (let i = 0; i < lit.length; i++) {
      if (this.lights[i] === lit[i].light && Math.abs(this.weights[i] - lit[i].weight) < WEIGHT_STEP) continue;
      this.lights[i] = lit[i].light;
      this.weights[i] = lit[i].weight;
      changed = true;
    }
    this.lights.length = lit.length;
    return changed;
  }
}

function addTexture(scene: Phaser.Scene): void {
  if (scene.textures.exists(TEXTURE)) return;
  const { width, height, rgba, frames } = critterSheet();
  const texture = scene.textures.createCanvas(TEXTURE, width, height)!;
  texture.context.putImageData(new ImageData(rgba, width, height), 0, 0);
  texture.refresh();
  texture.setFilter(Phaser.Textures.FilterMode.NEAREST);
  for (const { name, kind, x, y } of frames) {
    texture.add(name, 0, x, y, CRITTER_BOXES[kind].width, CRITTER_BOXES[kind].height);
  }
}
