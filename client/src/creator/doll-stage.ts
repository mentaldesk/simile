import Phaser from 'phaser';
import type { DollManifest } from '../dolls/manifest';
import { makeDoll, type PaperDoll } from '../dolls/paper-doll';
import type { Facing } from '../net';
import { TILE_M } from '../side/layout';
import { WALK_CYCLE_M } from '../side/motion';
import { WALKING_SPEED } from '../world/tuning';

const FACINGS: Facing[] = ['east', 'south', 'north'];
/** CSS px. */
const DOLL_HEIGHT = 150;
const CELL_WIDTH = DOLL_HEIGHT * 0.62;
const GROUND = DOLL_HEIGHT * 1.08;
const HEIGHT = DOLL_HEIGHT * 1.15;
const WALK_SECONDS = WALK_CYCLE_M / (WALKING_SPEED * TILE_M);

/** The look's doll walking from the side, the front and the back, in a small game of its own. */
export class DollStage {
  private readonly game: Phaser.Game;
  private readonly ready: Promise<Phaser.Scene>;
  private readonly ratio = window.devicePixelRatio || 1;
  private dolls: PaperDoll[] = [];
  private shown?: string;
  private count = 0;

  constructor(parent: HTMLElement) {
    let started!: (scene: Phaser.Scene) => void;
    this.ready = new Promise((resolve) => (started = resolve));
    const walk = (time: number) =>
      this.dolls.forEach((doll, i) => doll.setPose('walking', FACINGS[i], time / 1000 / WALK_SECONDS));
    const { ratio } = this;
    this.game = new Phaser.Game({
      type: Phaser.AUTO,
      parent,
      width: Math.round(FACINGS.length * CELL_WIDTH * ratio),
      height: Math.round(HEIGHT * ratio),
      transparent: true,
      banner: false,
      audio: { noAudio: true },
      input: { keyboard: false, mouse: false, touch: false, gamepad: false },
      scale: { mode: Phaser.Scale.NONE, zoom: 1 / ratio },
      scene: {
        create(this: Phaser.Scene) {
          started(this);
        },
        update: (time: number) => walk(time),
      },
    });
  }

  async show(doll: DollManifest): Promise<void> {
    const scene = await this.ready;
    const id = `creator-${this.count++}`;
    const { ratio } = this;
    const at = (i: number) => (i + 0.5) * CELL_WIDTH * ratio;
    const made = await Promise.all(
      FACINGS.map((_, i) => makeDoll(scene, at(i), GROUND * ratio, id, doll, DOLL_HEIGHT * ratio)),
    );
    for (const old of this.dolls) old.destroy();
    if (this.shown) this.unload(scene, this.shown);
    this.dolls = made;
    this.shown = id;
  }

  destroy(): void {
    this.game.destroy(true);
  }

  private unload(scene: Phaser.Scene, id: string): void {
    for (const key of [`doll-${id}-flat`, `doll-${id}-painted`]) {
      if (scene.textures.exists(key)) scene.textures.remove(key);
    }
  }
}
