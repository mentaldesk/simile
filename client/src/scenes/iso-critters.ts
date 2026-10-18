import Phaser from 'phaser';
import { village } from '../world';
import {
  DEFAULT_HOUR,
  PIXEL_SCALE,
  SHADOW_DEPTH,
  simClock,
  type IsoTile,
  type LitLayer,
  type SceneryManifest,
} from '../world/iso';
import { CRITTER_BOXES, critterSheet } from '../world/iso/critter-art';
import { CritterLight } from '../world/iso/critter-light';
import { CRITTERS, Critters, Water, type CritterTuning } from '../world/iso/critters';

const TEXTURE = 'iso-critters';
/** Flat on the water: over the ground and shadows, under everything standing. */
const RING_DEPTH = SHADOW_DEPTH + 0.5;
/** Reading the sim clock allocates, so in between it's run on here. */
const CLOCK_SECONDS = 1;

export class IsoCritters {
  private readonly critters: Critters;
  private readonly sprites: Phaser.GameObjects.Image[];
  private readonly tile: IsoTile;
  private readonly waterMetres: number;
  private readonly light: CritterLight;
  private shown = false;
  private sinceClock = Infinity;

  constructor(scene: Phaser.Scene, manifest: SceneryManifest, tuning: CritterTuning = CRITTERS) {
    addTexture(scene);
    this.tile = manifest.tile;
    this.waterMetres = manifest.ground.heights.water ?? 0;
    this.critters = new Critters(Water.of(village), tuning);
    this.light = new CritterLight(village.width, village.height);
    this.sprites = this.critters.all.map(({ kind, frame }) => {
      const { width, height, anchor } = CRITTER_BOXES[kind];
      return scene.add
        .image(0, 0, TEXTURE, frame)
        .setOrigin(anchor.x / width, anchor.y / height)
        .setScale(PIXEL_SCALE)
        .setVisible(false);
    });
  }

  draw(dt: number, lit: readonly LitLayer[] | undefined): void {
    if (!lit) {
      if (this.shown) for (const sprite of this.sprites) sprite.setVisible(false);
      this.shown = false;
      return;
    }
    this.shown = true;
    const { critters } = this;
    if ((this.sinceClock += dt) >= CLOCK_SECONDS) {
      this.sinceClock = 0;
      critters.hour = simClock.hour() ?? DEFAULT_HOUR;
    } else {
      const hour = critters.hour + (dt * simClock.speed) / 3600;
      critters.hour = hour < 24 ? hour : hour - 24;
    }
    critters.update(dt);
    const { all } = critters;
    const { width, height, px_per_metre_up } = this.tile;
    for (let i = 0; i < all.length; i++) {
      const critter = all[i];
      const sprite = this.sprites[i];
      if (sprite.visible !== critter.visible) sprite.setVisible(critter.visible);
      if (!critter.visible) continue;
      const { x, y } = critter;
      if (sprite.frame.name !== critter.frame) sprite.setFrame(critter.frame, false, false);
      if (sprite.alpha !== critter.alpha) sprite.setAlpha(critter.alpha);
      const ground = whole(((x + y) * height) / 2);
      const left = whole(((x - y) * width) / 2);
      const top = whole(ground - (this.waterMetres + critter.z) * px_per_metre_up);
      if (sprite.x !== left || sprite.y !== top) sprite.setPosition(left, top);
      const depth = critter.kind === 'ripple' ? RING_DEPTH : ground;
      if (sprite.depth !== depth) sprite.setDepth(depth);
      const tint = this.light.colourAt(lit, critter);
      if (sprite.tintTopLeft !== tint) sprite.setTint(tint);
    }
  }
}

/** Rounded, as an integer, which V8 keeps unboxed. */
function whole(value: number): number {
  const half = value + 0.5;
  return (half | 0) > half ? (half | 0) - 1 : half | 0;
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
