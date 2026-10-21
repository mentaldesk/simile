import Phaser from 'phaser';
import { isFigure, type DollManifest } from '../dolls/manifest';
import { makeDoll } from '../dolls/paper-doll';
import type { DollPose, PoseOptions } from '../dolls/rig';
import { makeFigure } from '../dolls/sprite-figure';
import type { Facing } from '../net';
import { TILE_M } from '../side/layout';
import { CLIMB_CYCLE_M, CLIMB_SPEED, RUN_CYCLE_M, WALK_CYCLE_M } from '../side/motion';
import { WALKING_SPEED } from '../world/tuning';

/** CSS px. */
const DOLL_HEIGHT = 150;
const CELL_WIDTH = DOLL_HEIGHT * 0.62;
const GROUND = DOLL_HEIGHT * 1.08;
const HEIGHT = DOLL_HEIGHT * 1.15;
const WALK_SECONDS = WALK_CYCLE_M / (WALKING_SPEED * TILE_M);
const RUN_SECONDS = RUN_CYCLE_M / (2 * WALKING_SPEED * TILE_M);
const CLIMB_SECONDS = CLIMB_CYCLE_M.ladder / (CLIMB_SPEED.ladder * TILE_M);

type Cell = { pose: DollPose; facing: Facing; seconds: number; options?: PoseOptions };
type Posable = Phaser.GameObjects.Container & {
  setPose(pose: DollPose, facing: Facing, phase?: number, options?: PoseOptions): unknown;
};

/** The flat doll walking from the side, the front and the back. */
const FLAT: Cell[] = (['east', 'south', 'north'] as const).map((facing) => ({
  pose: 'walking',
  facing,
  seconds: WALK_SECONDS,
}));
/** The painted figure walking, running and climbing a ladder. */
const PAINTED: Cell[] = [
  { pose: 'walking', facing: 'east', seconds: WALK_SECONDS },
  { pose: 'walking', facing: 'east', seconds: RUN_SECONDS, options: { run: 1 } },
  { pose: 'climbing', facing: 'north', seconds: CLIMB_SECONDS, options: { on: 'ladder' } },
];

/** The look's doll, or its painted figure once there is one, in a small game of its own. */
export class DollStage {
  private readonly game: Phaser.Game;
  private readonly ready: Promise<Phaser.Scene>;
  private readonly ratio = window.devicePixelRatio || 1;
  private shown: [Posable, Cell][] = [];
  private textures: string[] = [];
  private count = 0;

  constructor(parent: HTMLElement) {
    let started!: (scene: Phaser.Scene) => void;
    this.ready = new Promise((resolve) => (started = resolve));
    const move = (time: number) => {
      for (const [made, cell] of this.shown) {
        made.setPose(cell.pose, cell.facing, time / 1000 / cell.seconds, cell.options);
      }
    };
    const { ratio } = this;
    this.game = new Phaser.Game({
      type: Phaser.AUTO,
      parent,
      width: Math.round(FLAT.length * CELL_WIDTH * ratio),
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
        update: (time: number) => move(time),
      },
    });
  }

  async show(doll: DollManifest): Promise<void> {
    const scene = await this.ready;
    const id = `creator-${this.count++}`;
    const { ratio } = this;
    const at = (i: number) => (i + 0.5) * CELL_WIDTH * ratio;
    const cells = isFigure(doll) ? PAINTED : FLAT;
    const made: Posable[] = await Promise.all(
      cells.map((_, i) =>
        isFigure(doll)
          ? makeFigure(scene, at(i), GROUND * ratio, id, doll, DOLL_HEIGHT * ratio)
          : makeDoll(scene, at(i), GROUND * ratio, id, doll, DOLL_HEIGHT * ratio),
      ),
    );
    for (const [old] of this.shown) old.destroy();
    for (const key of this.textures) if (scene.textures.exists(key)) scene.textures.remove(key);
    this.shown = made.map((figure, i) => [figure, cells[i]]);
    this.textures = [isFigure(doll) ? `figure-${id}` : `doll-${id}-flat`];
  }

  destroy(): void {
    this.game.destroy(true);
  }
}
