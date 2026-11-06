import Phaser from 'phaser';
import type { CreatureKind } from '../../net';
import { DEPTH } from '../depths';
import { feetOf, PPM, xOf } from '../layout';
import type { Village } from '../maps';
import { sideCreatures, type Creatures } from './creatures';
import { creatureFigures, flinchOf, frameOf, goingDown, placedOf, type CreatureManifest } from './figures';

const HURT_TINT = 0xff9a8a;
const FLASH_TINT = 0xffffff;

function addAtlas(scene: Phaser.Scene, key: string, figure: CreatureManifest): Promise<void> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => {
      if (!scene.textures.exists(key)) {
        const texture = scene.textures.addImage(key, image)!;
        texture.setFilter(Phaser.Textures.FilterMode.LINEAR);
        for (const [name, { frame }] of Object.entries(figure.frames)) texture.add(name, 0, ...frame);
      }
      resolve();
    };
    image.onerror = () => reject(new Error(`Couldn't load the ${figure.id} atlas`));
    image.src = figure.painted;
  });
}

/** The creatures on the street shown and its floors, drawn from their painted figures. */
export class CreatureView {
  private readonly images = new Map<string, Phaser.GameObjects.Image>();
  private readonly loaded = new Set<CreatureKind>();
  private readonly loading = new Set<CreatureKind>();
  private readonly scene: Phaser.Scene;
  private readonly creatures: Creatures;

  constructor(scene: Phaser.Scene, creatures: Creatures = sideCreatures) {
    this.scene = scene;
    this.creatures = creatures;
  }

  /** `from` is the street cell a hit knocks them back from: the player's. */
  update(village: Village, street: string, tint: number, dt: number, from: number): void {
    this.creatures.update(dt);
    for (const [id, image] of this.images) {
      if (!this.creatures.all.has(id)) {
        image.destroy();
        this.images.delete(id);
      }
    }
    for (const [id, tracked] of this.creatures.all) {
      const map = village.map(tracked.map);
      const kind = tracked.creature.kind;
      const figure = creatureFigures[kind];
      const image = this.images.get(id);
      if (!figure || !map || map.street !== street || !this.ready(kind, figure)) {
        image?.setVisible(false);
        continue;
      }
      const drawn = image ?? this.add(id, kind);
      const frame = frameOf(figure, tracked);
      const { originX, originY, flip } = placedOf(figure, frame, tracked.facing);
      const going = tracked.down === undefined ? undefined : goingDown(figure, tracked.facing, tracked.down);
      const { back, flash } = flinchOf(tracked.hit);
      const across = map.offset.x + tracked.at.x;
      const away = Math.sign(across - from) || (tracked.facing === 'east' ? -1 : 1);
      const x = xOf(across + back * away);
      const y = feetOf(map.offset.y + tracked.at.y + (going?.drop ?? 0));
      const depth = map.kind === 'floor' ? DEPTH.insideDoll : DEPTH.doll;
      drawn
        .setVisible(true)
        .setFrame(frame)
        .setOrigin(originX, originY)
        .setFlipX(flip)
        .setPosition(x, y)
        .setDepth(depth - 0.5 + y * 1e-7)
        .setAngle(going?.angle ?? 0)
        .setAlpha(going?.alpha ?? 1)
        .setTint(tracked.state === 'hurt' ? HURT_TINT : tint);
      if (flash) drawn.setTintFill(FLASH_TINT);
    }
  }

  destroy(): void {
    for (const image of this.images.values()) image.destroy();
    this.images.clear();
  }

  private ready(kind: CreatureKind, figure: CreatureManifest): boolean {
    if (this.loaded.has(kind)) return true;
    if (!this.loading.has(kind)) {
      this.loading.add(kind);
      addAtlas(this.scene, `creature-${kind}`, figure).then(
        () => this.loaded.add(kind),
        (error: unknown) => console.warn(error),
      );
    }
    return false;
  }

  private add(id: string, kind: CreatureKind): Phaser.GameObjects.Image {
    const figure = creatureFigures[kind]!;
    const image = this.scene.add.image(0, 0, `creature-${kind}`).setScale(PPM / figure.ppm);
    this.images.set(id, image);
    return image;
  }
}
